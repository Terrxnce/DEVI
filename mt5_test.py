python - <<EOF
import MetaTrader5 as mt5
mt5.initialize()
print([s.name for s in mt5.symbols_get("EURUSD*")])
mt5.shutdown()
EOF
