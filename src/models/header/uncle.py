from core.models import LbeSchema
from core.types import HexBytes


class UncleHeader(LbeSchema):
    """A competing block referenced by a canonical block (Bedrock uncle reference).

    Only the header identity is kept: the uncle block itself is usually also
    stored (the node streams competing blocks), so the block page can link to it.
    """

    hash: HexBytes
    parent_block: HexBytes
    slot: int
    block_root: HexBytes
    leader_key: HexBytes
