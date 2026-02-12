from typing import Annotated

from pydantic import Field

from core.models import NbeSchema
from models.transactions.operations.contents import OperationContent
from models.transactions.operations.proofs import OperationProof


class Operation(NbeSchema):
    content: Annotated[OperationContent, Field(discriminator="type")]
    proof: Annotated[OperationProof, Field(discriminator="type")]
