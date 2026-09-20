from core.annotate import FileBlock
from core.pack import pack


def test_pack_keeps_all_files_when_under_budget():
    # Arrange: two tiny sample blocks, each estimated at 2 tokens.
    blocks = [
        FileBlock(path="Source/App.swift", tier="comment", text="abcd"),
        FileBlock(path="README.md", tier="context", text="efgh"),
    ]

    # Act: pack them with a generous budget of 10 tokens.
    result = pack(blocks, budget_tokens=10)

    # Assert: both blocks survive, in their original order.
    assert result.included == blocks
    assert result.excluded == []
    assert result.total_tokens == 4
    assert result.stopped_early is False
    assert result.payload() == "abcd\n\nefgh"


def test_pack_keeps_file_when_cost_equals_budget():
    # Six characters cost exactly 2 estimated tokens.
    blocks = [
        FileBlock(path="Source/App.swift", tier="comment", text="abcdef"),
    ]

    result = pack(blocks, budget_tokens=2)

    assert result.included == blocks
    assert result.excluded == []
    assert result.total_tokens == 2
    assert result.stopped_early is False
    assert result.payload() == "abcdef"


def test_pack_stops_when_file_exceeds_remaining_budget():
    blocks = [
        FileBlock(path="Source/First.swift", tier="comment", text="abc"),
        FileBlock(path="Source/Large.swift", tier="comment", text="abcdefghi"),
        FileBlock(path="Source/Last.swift", tier="comment", text="xyz"),
    ]

    result = pack(blocks, budget_tokens=3)

    assert result.included == [blocks[0]]
    assert result.total_tokens == 1
    assert result.stopped_early is True
    assert result.payload() == "abc"

    assert [item.path for item in result.excluded] == [
        "Source/Large.swift",
        "Source/Last.swift",
    ]
    assert result.excluded[0].reason == "exceeds remaining budget"
    assert result.excluded[1].reason == "budget exhausted before reached"
