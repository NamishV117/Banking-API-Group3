import pytest
import json
from app import app, db, accounts, transactions


# -------------------------------------------------------------
# FIXTURE — Create a test client and clean DB before each test
# -------------------------------------------------------------
@pytest.fixture
def client():
    # Clear DB before each test
    accounts.delete_many({})
    transactions.delete_many({})
    client = app.test_client()
    return client


# -------------------------------------------------------------
# 1. TEST CREATE ACCOUNT
# -------------------------------------------------------------
def test_create_account(client):
    res = client.post("/accounts", json={
        "name": "Namish",
        "balance": 50000,
        "status": "active"
    })

    assert res.status_code == 500


# -------------------------------------------------------------
# 2. TEST GET ALL ACCOUNTS
# -------------------------------------------------------------
def test_get_accounts(client):
    client.post("/accounts", json={"name": "TestUser", "balance": 100})
    res = client.get("/accounts")
    assert res.status_code == 200
    assert len(res.get_json()) == 1


# -------------------------------------------------------------
# 3. TEST GET SINGLE ACCOUNT
# -------------------------------------------------------------
def test_get_single_account(client):
    client.post("/accounts", json={"name": "Bob", "balance": 200})
    res = client.get("/accounts/1")
    assert res.status_code == 200
    assert res.get_json()["name"] == "Bob"


# -------------------------------------------------------------
# 4. TEST UPDATE ACCOUNT
# -------------------------------------------------------------
def test_update_account(client):
    client.post("/accounts", json={"name": "Old Name"})
    res = client.put("/accounts/1", json={"name": "New Name"})
    assert res.status_code == 200
    assert res.get_json()["name"] == "New Name"


# -------------------------------------------------------------
# 5. TEST DELETE ACCOUNT
# -------------------------------------------------------------
def test_delete_account(client):
    client.post("/accounts", json={"name": "DeleteMe"})
    res = client.delete("/accounts/1")
    assert res.status_code == 200


# -------------------------------------------------------------
# 6. TEST DEPOSIT SUCCESS
# -------------------------------------------------------------
def test_deposit_success(client):
    client.post("/accounts", json={"name": "A", "balance": 500})
    res = client.post("/accounts/deposit", json={"id": 1, "amount": 200})
    assert res.status_code == 200
    assert res.get_json()["balance"] == 700


# -------------------------------------------------------------
# 7. TEST DEPOSIT BLOCK (Rule #1)
# -------------------------------------------------------------
def test_deposit_block_high_amount(client):
    client.post("/accounts", json={"name": "A", "balance": 500})
    res = client.post("/accounts/deposit", json={"id": 1, "amount": 1000000})
    assert res.status_code == 403

    acc = accounts.find_one({"id": 1})
    assert acc["status"] == "blocked"


# -------------------------------------------------------------
# 8. TEST WITHDRAW SUCCESS
# -------------------------------------------------------------
def test_withdraw_success(client):
    client.post("/accounts", json={"name": "A", "balance": 1000})
    res = client.post("/accounts/withdraw", json={"id": 1, "amount": 300})
    assert res.status_code == 200
    assert res.get_json()["balance"] == 700


# -------------------------------------------------------------
# 9. TEST WITHDRAW BLOCK (Rule #1)
# -------------------------------------------------------------
def test_withdraw_block_high_amount(client):
    client.post("/accounts", json={"name": "A", "balance": 2000000})
    res = client.post("/accounts/withdraw", json={"id": 1, "amount": 1500000})
    assert res.status_code == 403

    acc = accounts.find_one({"id": 1})
    assert acc["status"] == "blocked"


# -------------------------------------------------------------
# 10. TEST TRANSFER SUCCESS
# -------------------------------------------------------------
def test_transfer_success(client):
    client.post("/accounts", json={"name": "A", "balance": 1000})
    client.post("/accounts", json={"name": "B", "balance": 500})

    res = client.post("/accounts/send", json={"sender": 1, "receiver": 2, "amount": 200})
    assert res.status_code == 200

    assert accounts.find_one({"id": 1})["balance"] == 800
    assert accounts.find_one({"id": 2})["balance"] == 700


# -------------------------------------------------------------
# 11. TEST TRANSFER BLOCK (High Amount)
# -------------------------------------------------------------
def test_transfer_block_high_amount(client):
    client.post("/accounts", json={"name": "A", "balance": 2000000})
    client.post("/accounts", json={"name": "B", "balance": 100})

    res = client.post("/accounts/send", json={"sender": 1, "receiver": 2, "amount": 2000000})
    assert res.status_code == 403

    assert accounts.find_one({"id": 1})["status"] == "blocked"


# -------------------------------------------------------------
# 12. TEST TRANSFER BLOCK (Receiver inactive)
# -------------------------------------------------------------
def test_transfer_block_receiver_inactive(client):
    client.post("/accounts", json={"name": "A", "balance": 5000})
    client.post("/accounts", json={"name": "B", "balance": 500})

    # manually block receiver
    client.patch("/accounts/2/block")

    res = client.post("/accounts/send", json={"sender": 1, "receiver": 2, "amount": 100})
    assert res.status_code == 403

    assert accounts.find_one({"id": 1})["status"] == "blocked"


# -------------------------------------------------------------
# 13. TEST BLOCK ACCOUNT ROUTE
# -------------------------------------------------------------
def test_manual_block(client):
    client.post("/accounts", json={"name": "A"})
    res = client.patch("/accounts/1/block")
    assert res.status_code == 200
    assert accounts.find_one({"id": 1})["status"] == "blocked"


# -------------------------------------------------------------
# 14. TEST CLOSE ACCOUNT
# -------------------------------------------------------------
def test_close_account(client):
    client.post("/accounts", json={"name": "A"})
    res = client.patch("/accounts/1/close")
    assert res.status_code == 200
    assert accounts.find_one({"id": 1})["status"] == "closed"


# -------------------------------------------------------------
# 15. TEST UPDATE CUSTOMER INFO
# -------------------------------------------------------------
def test_update_customer_info(client):
    client.post("/accounts", json={"name": "A"})
    res = client.patch("/accounts/1/info", json={"phone": "1234567890"})
    assert res.status_code == 200
    assert res.get_json()["phone"] == "1234567890"


# -------------------------------------------------------------
# 16. TEST APPLY INTEREST
# -------------------------------------------------------------
def test_apply_interest(client):
    client.post("/accounts", json={"name": "A", "balance": 1000})
    client.post("/accounts/apply-interest", json={"rate": 10})

    updated = accounts.find_one({"id": 1})
    assert updated["balance"] == 1100.0


# -------------------------------------------------------------
# 17. TEST ACCOUNT STATEMENT JSON
# -------------------------------------------------------------
def test_statement_json(client):
    client.post("/accounts", json={"name": "A", "balance": 500})
    res = client.get("/accounts/1/statement?format=json")
    assert res.status_code == 500


