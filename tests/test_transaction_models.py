import pytest
from models.transactions.transaction import Transaction
from core.types import HexBytes

def test_transaction_validation_with_unknown_types():
    # This data simulates what is produced by SignedTransactionSerializer.into_transaction()
    # when it encounters unknown opcodes or proofs.
    transaction_data = {
        "hash": HexBytes(b"\x01" * 32),
        "operations": [
            {
                "content": {
                    "type": "UnknownOp",
                    "opcode": 123,
                    "raw_payload": {"some": "data"}
                },
                "proof": {
                    "type": "Unknown",
                    "signature": HexBytes(b"\x02" * 64)
                }
            }
        ],
        "execution_gas_price": 100,
        "storage_gas_price": 200
    }
    
    tx = Transaction.model_validate(transaction_data)
    
    assert tx.hash == HexBytes(b"\x01" * 32)
    assert tx.operations[0].content.type == "UnknownOp"
    assert tx.operations[0].content.opcode == 123
    assert tx.operations[0].proof.type == "Unknown"
    assert tx.operations[0].proof.signature == HexBytes(b"\x02" * 64)

if __name__ == "__main__":
    test_transaction_validation_with_unknown_types()
    print("Test passed!")
