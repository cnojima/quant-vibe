#!/bin/bash
# Check for naive datetime usage in critical files

if grep -n "datetime\.utcnow()" "$@"; then
    echo "ERROR: Found datetime.utcnow() - use now_utc() instead"
    exit 1
fi

if grep -n "datetime\.now()" "$@" | grep -v "strftime\|# display"; then
    echo "WARNING: Found datetime.now() - verify it's not used for data persistence"
    echo "Use now_utc() for timestamps stored in DB/Redis"
    exit 1
fi

exit 0
