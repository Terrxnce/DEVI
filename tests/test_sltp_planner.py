from decimal import Decimal
import unittest

from core.orchestration.structure_exit_planner import StructureExitPlanner


class TestSLTPPlanner(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "sltp_planning": {
                "enabled": True,
                "exit_priority": ["order_block", "fair_value_gap", "atr"],
                "atr_fallback_enabled": True,
                "buffers": {
                    "sl_atr_buffer": 0.15,
                    "tp_extension_atr": 1.0,
                    "min_buffer_pips": 1.0,
                    "max_buffer_pips": 10.0,
                },
                "min_rr_gate": 1.5,
            }
        }
        self.broker = {
            "digits": 5,
            "point": "0.00001",
            "min_stop_distance": "0.00020",
        }
        self.planner = StructureExitPlanner(self.cfg, self.broker)

    def D(self, x):
        return Decimal(str(x))

    # OB happy path BUY
    def test_ob_happy_path_buy(self):
        entry = self.D(1.10000)
        atr = self.D(0.00100)
        structures = {
            "order_block": {
                "nearest": {
                    "upper_edge": self.D(1.10100),
                    "lower_edge": self.D(1.09900),
                    "side": "BUY",
                    "age": 5,
                    "quality": self.D(0.8),
                }
            },
            # Opposing target (SELL OB) given via same key per spec simplification
            "fair_value_gap": {"nearest": None},
        }
        planned = self.planner.plan("BUY", entry, atr, structures)
        self.assertIsNotNone(planned)
        self.assertEqual(planned["method"], "order_block")
        self.assertLess(planned["sl"], entry)
        self.assertGreater(planned["tp"], entry)
        self.assertGreaterEqual(planned["expected_rr"], self.D(1.5))

    # FVG happy path SELL
    def test_fvg_happy_path_sell(self):
        entry = self.D(1.20500)
        atr = self.D(0.00120)
        structures = {
            "fair_value_gap": {
                "nearest": {
                    "gap_low": self.D(1.20200),
                    "gap_high": self.D(1.20600),
                    "side": "SELL",
                    "age": 7,
                    "quality": self.D(0.7),
                }
            }
        }
        planned = self.planner.plan("SELL", entry, atr, structures)
        self.assertIsNotNone(planned)
        self.assertEqual(planned["method"], "fair_value_gap")
        self.assertGreater(planned["sl"], entry)
        self.assertLess(planned["tp"], entry)
        self.assertGreaterEqual(planned["expected_rr"], self.D(1.5))

    # ATR fallback
    def test_atr_fallback_when_no_structures(self):
        entry = self.D(1.30000)
        atr = self.D(0.00100)
        structures = {}
        planned = self.planner.plan("BUY", entry, atr, structures)
        self.assertIsNotNone(planned)
        self.assertEqual(planned["method"], "atr")
        self.assertLess(planned["sl"], entry)
        self.assertGreater(planned["tp"], entry)

    # Broker min_stop_distance enforced
    def test_min_stop_distance_enforced(self):
        entry = self.D(1.40000)
        atr = self.D(0.00010)  # tiny ATR
        structures = {}
        planned = self.planner.plan("SELL", entry, atr, structures)
        self.assertIsNotNone(planned)
        # Distances must be >= min_stop_distance
        d_sl = abs(planned["sl"] - entry)
        d_tp = abs(entry - planned["tp"])
        self.assertGreaterEqual(d_sl, Decimal(self.broker["min_stop_distance"]))
        self.assertGreaterEqual(d_tp, Decimal(self.broker["min_stop_distance"]))

    # Post-clamp RR fail -> None
    def test_post_clamp_rr_fail(self):
        # Configure very large min_stop_distance to force small reward vs large risk
        broker = {
            "digits": 5,
            "point": "0.00001",
            "min_stop_distance": "0.00500",  # 50 pips
        }
        planner = StructureExitPlanner(self.cfg, broker)
        entry = self.D(1.50000)
        atr = self.D(0.00050)
        planned = planner.plan("BUY", entry, atr, {})
        # With large min stop, risk likely big and reward small due to clamps; expect rejection
        self.assertIsNone(planned)

    # Rounding to point for 5 digits
    def test_rounding_precision(self):
        entry = self.D(1.11111)
        atr = self.D(0.00123)
        planned = self.planner.plan("BUY", entry, atr, {})
        self.assertIsNotNone(planned)
        point = Decimal(self.broker["point"])  # 1e-5
        sl_units = (planned["sl"] / point)
        tp_units = (planned["tp"] / point)
        # Should be integers when divided by point
        self.assertEqual(sl_units, sl_units.quantize(0))
        self.assertEqual(tp_units, tp_units.quantize(0))


if __name__ == "__main__":
    unittest.main()
