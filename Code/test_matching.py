"""Tests for standardized mean differences."""
import unittest

import numpy as np
import pandas as pd

from analysis_engine import compute_smd


class StandardizedDifferenceTests(unittest.TestCase):
    def test_shifted_constants_are_not_balanced(self):
        data=pd.DataFrame({'group':[1,1,0,0],'x':[2.,2.,1.,1.]})
        self.assertEqual(compute_smd(data,'group',['x'])['x'],np.inf)
        data['x']=-data.x
        self.assertEqual(compute_smd(data,'group',['x'])['x'],-np.inf)

    def test_identical_constants_have_zero_difference(self):
        data=pd.DataFrame({'group':[1,1,0,0],'x':[2.,2.,2.,2.]})
        self.assertEqual(compute_smd(data,'group',['x'])['x'],0.)

    def test_pooled_sample_standard_deviation(self):
        data=pd.DataFrame({'group':[1,1,0,0],'x':[2.,4.,0.,2.]})
        self.assertAlmostEqual(compute_smd(data,'group',['x'])['x'],np.sqrt(2.))

    def test_undersized_groups_are_rejected(self):
        data=pd.DataFrame({'group':[1,0],'x':[2.,1.]})
        with self.assertRaisesRegex(ValueError,'at least two'):
            compute_smd(data,'group',['x'])


if __name__=='__main__':
    unittest.main()
