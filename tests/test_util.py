import unittest

from webmo.util import get_geometry, xtb_geometry


class XtbGeometryTest(unittest.TestCase):
    def test_xyz_lines_become_a_coord_block(self):
        self.assertEqual(xtb_geometry("O 0 0 0.117\nH\t0.0\t0.757\t-0.467\n"),
                         "$coord angs\n    0.000000    0.000000    0.117000   O\n"
                         "    0.000000    0.757000   -0.467000   H")

    def test_atomic_numbers_are_dropped(self):
        self.assertEqual(xtb_geometry("O 8 0.0 0.0 0.117"), "$coord angs\n    0.000000    0.000000    0.117000   O")

    def test_coord_block_is_unchanged(self):
        block = "$coord angs\n 0.0 0.0 0.117 O"
        self.assertEqual(xtb_geometry(block + "\n\n"), block, "blank lines would end xtb's $coord")

    def test_other_text_is_refused(self):
        with self.assertRaises(ValueError):
            xtb_geometry("C\nH 1 1.09")

    def test_get_geometry_xtb_format(self):
        results = {"symbols": ["He"], "geometry": [0.0, 0.0, 0.0]}
        self.assertEqual(get_geometry(results), "He\t0.000000\t0.000000\t0.000000\n")
        self.assertEqual(get_geometry(results, xtb_format=True),
                         "$coord angs\n    0.000000    0.000000    0.000000   He")


if __name__ == "__main__":
    unittest.main()
