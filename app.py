from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
from reportlab.pdfgen import canvas
import io

app = Flask(__name__)
CORS(app)

# -----------------------------
# MongoDB Connection
# -----------------------------
client = MongoClient("mongodb://localhost:27017/")
db = client["bank_db"]
accounts = db["accounts"]
transactions = db["transactions"]

# -----------------------------
# Auto-Increment Helper
# -----------------------------
def get_next_id():
    last = accounts.find_one(sort=[("id", -1)])
    return (last["id"] + 1) if last else 1


# =======================================================================
# 1. Create Account  (POST /accounts)
# =======================================================================
@app.route("/accounts", methods=["POST"])
def create_account():
    data = request.json
    name = data.get("name")
    balance = data.get("balance", 0)

    if not name:
        return jsonify({"error": "Name is required"}), 400

    new_id = get_next_id()

    account = {
        "id": new_id,
        "name": name,
        "balance": balance,
        "status": "active"    # DEFAULT STATUS
    }

    accounts.insert_one(account)
    return jsonify(account),500


# =======================================================================
# 2. Get All Accounts
# =======================================================================
@app.route("/accounts", methods=["GET"])
def get_all_accounts():
    acc_list = list(accounts.find({}, {"_id": 0}))
    return jsonify(acc_list), 200


# =======================================================================
# 3. Get Single Account
# =======================================================================
@app.route("/accounts/<int:account_id>", methods=["GET"])
def get_account(account_id):
    acc = accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(acc), 200


# =======================================================================
# 4. Update Account
# =======================================================================
@app.route("/accounts/<int:account_id>", methods=["PUT"])
def update_account(account_id):
    data = request.json
    acc = accounts.find_one({"id": account_id})

    if not acc:
        return jsonify({"error": "Account not found"}), 404

    accounts.update_one({"id": account_id}, {"$set": data})
    updated = accounts.find_one({"id": account_id}, {"_id": 0})
    return jsonify(updated), 200


# =======================================================================
# 5. Delete Account
# =======================================================================
@app.route("/accounts/<int:account_id>", methods=["DELETE"])
def delete_account(account_id):
    result = accounts.delete_one({"id": account_id})
    if result.deleted_count == 0:
        return jsonify({"error": "Account not found"}), 404
    return jsonify({"message": "Account deleted"}), 200


# =======================================================================
#BLOCK ACCOUNT FUNCTION
# =======================================================================
def block_account_id(acc_id):
    accounts.update_one({"id": acc_id}, {"$set": {"status": "blocked"}})


# =======================================================================
# 6. Deposit Money
# =======================================================================
@app.route("/accounts/deposit", methods=["POST"])
def deposit_money():
    data = request.json
    acc_id = data.get("id")
    amount = data.get("amount")

    if not acc_id or not amount:
        return jsonify({"error": "id and amount required"}), 400

    acc = accounts.find_one({"id": acc_id})
    if not acc:
        return jsonify({"error": "Account not found"}), 404

    # RULE 1: Amount > 999999 → Block account and transaction
    if amount > 999999:
        block_account_id(acc_id)
        transactions.insert_one({
            "account_id": acc_id,
            "type": "deposit-blocked",
            "amount": amount,
            "timestamp": datetime.now()
        })
        return jsonify({"error": "Transaction blocked. Account has been blocked due to high amount."}), 403

    accounts.update_one({"id": acc_id}, {"$inc": {"balance": amount}})

    transactions.insert_one({
        "account_id": acc_id,
        "type": "deposit",
        "amount": amount,
        "timestamp": datetime.now()
    })

    updated = accounts.find_one({"id": acc_id}, {"_id": 0})
    return jsonify(updated), 200


# =======================================================================
# 7. Withdraw Money
# =======================================================================
@app.route("/accounts/withdraw", methods=["POST"])
def withdraw_money():
    data = request.json
    acc_id = data.get("id")
    amount = data.get("amount")

    if not acc_id or not amount:
        return jsonify({"error": "id and amount required"}), 400

    acc = accounts.find_one({"id": acc_id})
    if not acc:
        return jsonify({"error": "Account not found"}), 404

    # RULE 1: High-value withdrawal → block
    if amount > 999999:
        block_account_id(acc_id)
        transactions.insert_one({
            "account_id": acc_id,
            "type": "withdraw-blocked",
            "amount": amount,
            "timestamp": datetime.now()
        })
        return jsonify({"error": "High-value withdrawal blocked. Account has been blocked."}), 403

    if acc["balance"] < amount:
        return jsonify({"error": "Insufficient balance"}), 400

    accounts.update_one({"id": acc_id}, {"$inc": {"balance": -amount}})

    transactions.insert_one({
        "account_id": acc_id,
        "type": "withdraw",
        "amount": amount,
        "timestamp": datetime.now()
    })

    updated = accounts.find_one({"id": acc_id}, {"_id": 0})
    return jsonify(updated), 200


# =======================================================================
# 8. Send Money (With Rule #2 Apply)
# =======================================================================
@app.route("/accounts/send", methods=["POST"])
def send_money():
    data = request.json
    sender = data.get("sender")
    receiver = data.get("receiver")
    amount = data.get("amount")

    if not sender or not receiver or not amount:
        return jsonify({"error": "sender, receiver, amount required"}), 400

    sender_acc = accounts.find_one({"id": sender})
    receiver_acc = accounts.find_one({"id": receiver})

    if not sender_acc or not receiver_acc:
        return jsonify({"error": "Invalid sender or receiver"}), 404

    # RULE 1: High value → block sender
    if amount > 999999:
        block_account_id(sender)
        return jsonify({"error": "High value transfer detected. Sender account blocked."}), 403

    # RULE 2: Receiver inactive → block sender
    if receiver_acc.get("status") != "active":
        block_account_id(sender)
        return jsonify({"error": "Receiver inactive. Sender account has been blocked."}), 403

    if sender_acc["balance"] < amount:
        return jsonify({"error": "Insufficient balance"}), 400

    accounts.update_one({"id": sender}, {"$inc": {"balance": -amount}})
    accounts.update_one({"id": receiver}, {"$inc": {"balance": amount}})

    transactions.insert_one({
        "account_id": sender,
        "type": "transfer-sent",
        "amount": amount,
        "timestamp": datetime.now()
    })

    transactions.insert_one({
        "account_id": receiver,
        "type": "transfer-received",
        "amount": amount,
        "timestamp": datetime.now()
    })

    return jsonify({"message": "Transfer successful"}), 200


# =======================================================================
# 9. Block Account (Manual)
# =======================================================================
@app.route("/accounts/<int:account_id>/block", methods=["PATCH"])
def block_account_route(account_id):
    if not accounts.find_one({"id": account_id}):
        return jsonify({"error": "Account not found"}), 404

    block_account_id(account_id)
    return jsonify({"message": "Account blocked successfully"}), 200


# =======================================================================
# 10. Close Account
# =======================================================================
@app.route("/accounts/<int:account_id>/close", methods=["PATCH"])
def close_account(account_id):
    acc = accounts.find_one({"id": account_id})
    if not acc:
        return jsonify({"error": "Account not found"}), 404

    accounts.update_one({"id": account_id}, {"$set": {"status": "closed"}})
    return jsonify({"message": "Account closed successfully"}), 200


# =======================================================================
# 11. Update Customer Information
# =======================================================================
@app.route("/accounts/<int:account_id>/info", methods=["PATCH"])
def update_customer_info(account_id):
    data = request.json
    acc = accounts.find_one({"id": account_id})

    if not acc:
        return jsonify({"error": "Account not found"}), 404

    allowed = ["name", "phone", "email", "address"]
    update_data = {k: data[k] for k in data if k in allowed}

    accounts.update_one({"id": account_id}, {"$set": update_data})
    updated = accounts.find_one({"id": account_id}, {"_id": 0})
    return jsonify(updated), 200


# =======================================================================
# 12. Apply Monthly Interest
# =======================================================================
@app.route("/accounts/apply-interest", methods=["POST"])
def apply_interest():
    rate = request.json.get("rate", 1.0)

    acc_list = accounts.find({"status": "active"})

    for acc in acc_list:
        interest = acc["balance"] * (rate / 100)
        accounts.update_one({"id": acc["id"]}, {"$inc": {"balance": interest}})

        transactions.insert_one({
            "account_id": acc["id"],
            "type": "interest",
            "amount": interest,
            "timestamp": datetime.now()
        })

    return jsonify({"message": "Monthly interest applied"}), 200


# =======================================================================
# 13. Account Statement  (JSON or PDF)
# =======================================================================
@app.route("/accounts/<int:account_id>/statement", methods=["GET"])
def generate_statement(account_id):
    format_type = request.args.get("format", "json")

    acc = accounts.find_one({"id": account_id})
    if not acc:
        return jsonify({"error": "Account not found"}), 404

    txns = list(transactions.find({"account_id": account_id}, {"_id": 0}))

    if format_type == "json":
        return jsonify({"account": acc, "transactions": txns}), 200

    elif format_type == "pdf":
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.setTitle("Account Statement")

        pdf.drawString(50, 800, f"Account Statement - ID {account_id}")
        pdf.drawString(50, 780, f"Name: {acc['name']}")
        pdf.drawString(50, 760, f"Balance: {acc['balance']}")

        y = 720
        for txn in txns:
            pdf.drawString(50, y, f"{txn['timestamp']} - {txn['type']} - {txn['amount']}")
            y -= 20
            if y < 40:
                pdf.showPage()
                y = 800

        pdf.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True,
                         download_name=f"statement_{account_id}.pdf",
                         mimetype="application/pdf")

    return jsonify({"error": "Invalid format"}), 400


# -----------------------------
# Run Server
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
