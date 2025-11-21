#!/bin/bash
# Initialize Snowflake tables using credentials from secrets.toml

cd "$(dirname "$0")"

if [ ! -f .streamlit/secrets.toml ]; then
    echo "❌ Error: .streamlit/secrets.toml not found"
    exit 1
fi

echo "📖 Reading Snowflake credentials from secrets.toml..."
export SNOWFLAKE_ACCOUNT=$(grep 'SNOWFLAKE_ACCOUNT' .streamlit/secrets.toml | cut -d'"' -f2 | cut -d"'" -f2)
export SNOWFLAKE_USER=$(grep 'SNOWFLAKE_USER' .streamlit/secrets.toml | cut -d'"' -f2 | cut -d"'" -f2)
export SNOWFLAKE_PASSWORD=$(grep 'SNOWFLAKE_PASSWORD' .streamlit/secrets.toml | cut -d'"' -f2 | cut -d"'" -f2)
export SNOWFLAKE_WAREHOUSE=$(grep 'SNOWFLAKE_WAREHOUSE' .streamlit/secrets.toml | cut -d'"' -f2 | cut -d"'" -f2)
export SNOWFLAKE_DATABASE=$(grep 'SNOWFLAKE_DATABASE' .streamlit/secrets.toml | cut -d'"' -f2 | cut -d"'" -f2)
export SNOWFLAKE_SCHEMA=$(grep 'SNOWFLAKE_SCHEMA' .streamlit/secrets.toml | cut -d'"' -f2 | cut -d"'" -f2)

if [ -z "$SNOWFLAKE_ACCOUNT" ]; then
    echo "❌ Error: Could not extract SNOWFLAKE_ACCOUNT from secrets.toml"
    exit 1
fi

echo "✅ Found credentials for account: $SNOWFLAKE_ACCOUNT"
echo "🚀 Running schema initialization..."
python3 scripts/init_snowflake_schema.py

if [ $? -eq 0 ]; then
    echo "✅ Database initialization complete!"
else
    echo "❌ Database initialization failed"
    exit 1
fi
