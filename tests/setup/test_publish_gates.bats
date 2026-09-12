#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

CHECKER="${BATS_TEST_DIRNAME}/../../scripts/check-publish-gates.sh"
WORKFLOW="${BATS_TEST_DIRNAME}/../../.forgejo/workflows/ci.yml"

setup() {
    TEST_CWD="$(mktemp -d)"
    FIXTURE="${TEST_CWD}/ci.yml"
    cp "${WORKFLOW}" "${FIXTURE}"
}

teardown() {
    [[ -n "${TEST_CWD:-}" ]] && rm -rf "${TEST_CWD}"
}

remove_gate() {
    sed -i "/^[[:space:]]*-[[:space:]]*$1[[:space:]]*$/d" "${FIXTURE}"
}

@test "publication gate inventory accepts the committed workflow" {
    run -0 bash "${CHECKER}" "${FIXTURE}"
    [[ "${output}" == *"expected 19 same-workflow gates"* ]]
}

@test "publication gate inventory rejects each representative missing gate" {
    local gate
    for gate in drift-checks secrets-scan monitoring-config; do
        cp "${WORKFLOW}" "${FIXTURE}"
        remove_gate "${gate}"
        run bash "${CHECKER}" "${FIXTURE}"
        [ "${status}" -eq 1 ]
        [[ "${output}" == *"missing required gate: ${gate}"* ]]
    done
}

@test "publication gate inventory rejects an unexpected gate" {
    sed -i '/^      - validate-release-tag$/a\      - made-up-gate' "${FIXTURE}"
    run bash "${CHECKER}" "${FIXTURE}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"unexpected gate: made-up-gate"* ]]
}

@test "publication gate inventory rejects a missing workflow" {
    run bash "${CHECKER}" "${TEST_CWD}/missing.yml"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Workflow not found"* ]]
}
