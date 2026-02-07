# SCRIPTS BY ACTIVE USAGE

| Script Name | Purpose | Frequency |
|---|---|---|
| analyze_data_gaps.py | check bars tables for intraday gaps | as-needed |
| authorize_schwab.py | mint/refresh Schwab API tokens. Used by token_service | weekly |
| optimize_strategy.py | runs grid & walk-forward optimizations on a strategy | as-needed |
| run_* | start containerized services | daily |
| start_admin_ui_dev.sh | starts admin_ui/admin_ui_fe in DEV mode with hot-reloads | as-needed |
| sync_all.sh | executes sync_* scripts to sync moirae data with local | as-needed |
| sync_moirae_chunked.py | syncs options_bars in chunks from moirae | as-needed |
| sync_moirae.py | syncs options_bars in one-shot from moirae | as-needed |
| sync_tokens.sh | copies moirae's schwabdev_token.db to local | as-needed |
| sync_underlying.py | syncs underlying_bars table from moirae to local | as-needed |
