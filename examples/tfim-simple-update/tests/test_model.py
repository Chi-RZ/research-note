from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tfim_compare.model import square_bonds


def test_three_by_three_open_square_has_twelve_unique_bonds():
    bonds = square_bonds(3, 3)
    assert len(bonds) == 12
    assert len(set(bonds)) == 12
    assert all(a != b for a, b in bonds)
