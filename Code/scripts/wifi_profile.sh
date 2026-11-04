#!/bin/bash
# netctl reads a profile as shell: every value of wlan0-wifi is put in plain
# single quotes, whatever quotes (also typographic) people wrote.
#   wifi_profile.sh clean FILE      the profile with every value as 'value',
#                                   to stdout (start_wifi.sh -> /etc/netctl)
#   wifi_profile.sh get FILE KEY    one value without its quotes
#                                   (engines_build.sh)

QUOTES="\"|'|’|‘|“|”"

# stdin: a value; stdout: without surrounding spaces, and without its quotes
# only when there is one at BOTH ends (as a pair): quotes inside stay
# (hejhopp"nej), and so does a single one at one end only (hejhopp").
unquote() {
    sed -E -e 's/^[[:space:]]+//; s/[[:space:]]+$//' \
           -e "s/^($QUOTES)(.*)($QUOTES)\$/\\2/"
}

case "$1" in
    get)
        tr -d '\r' < "$2" | sed -n "s/^[[:space:]]*$3=//p" | tail -1 | unquote ;;
    clean)
        tr -d '\r' < "$2" | while IFS= read -r line || [ -n "$line" ]; do
            if [[ $line =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] \
                    && [[ ${BASH_REMATCH[2]} != \(* ]]; then
                key=${BASH_REMATCH[1]}
                value=$(printf '%s' "${BASH_REMATCH[2]}" | unquote)
                printf "%s='%s'\n" "$key" "${value//\'/\'\\\'\'}"
            else
                printf '%s\n' "$line"
            fi
        done ;;
    *) echo "usage: $0 clean FILE | get FILE KEY"; exit 2 ;;
esac
