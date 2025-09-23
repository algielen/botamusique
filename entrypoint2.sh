#!/usr/bin/env sh

command=$*

echo "Entrypoint will use $command"

if [ "$1" = "bash" ] || [ "$1" = "sh" ]; then
    exec "$@"
fi

if [ -n "$BAM_DB" ]; then
    command="$command --db $BAM_DB"
fi

if [ -n "$BAM_MUSIC_DB" ]; then
    command="$command --music-db $BAM_MUSIC_DB"
fi

if [ -n "$BAM_MUMBLE_SERVER" ]; then
    command="$command --server $BAM_MUMBLE_SERVER"
fi

if [ -n "$BAM_MUMBLE_PASSWORD" ]; then
    command="$command --password $BAM_MUMBLE_PASSWORD"
fi

if [ -n "$BAM_MUMBLE_PORT" ]; then
    command="$command --port $BAM_MUMBLE_PORT"
fi

if [ -n "$BAM_USER" ]; then
    command="$command --user $BAM_USER"
fi

if [ -n "$BAM_TOKENS" ]; then
    command="$command --tokens $BAM_TOKENS"
fi

if [ -n "$BAM_CHANNEL" ]; then
    command="$command --channel $BAM_CHANNEL"
fi

if [ -n "$BAM_CERTIFICATE" ]; then
    command="$command --cert $BAM_CERTIFICATE"
fi

if [ -n "$BAM_VERBOSE" ]; then
    command="$command --verbose"
fi

if [ -n "$BAM_BANDWIDTH" ]; then
    command="$command --bandwidth $BAM_BANDWIDTH"
fi

if [ -n "$BAM_CONFIG_FILE" ]; then
    command="$command --config $BAM_CONFIG_FILE"
fi

echo "Executing command $command"

# Finally execute
exec $command
