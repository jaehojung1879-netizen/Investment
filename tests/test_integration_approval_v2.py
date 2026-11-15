import hashlib

import pytest

from research.corporate_event_outcome_v1.input_pins_v2 import check_owner_comment


def sample():
    phrase = 'APPROVE SYN_ONLY ' + 'a' * 64
    comment = {'id': 123, 'user': {'login': 'jaehojung1879-netizen', 'id': 238918679},
               'issue_url': 'https://api.github.com/repos/jaehojung1879-netizen/Investment/issues/292',
               'created_at': '2026-11-10T10:00:00Z', 'body': phrase}
    auth = {'approvalCommentId': 123, 'approvalCommentSha256': hashlib.sha256(phrase.encode()).hexdigest(),
            'authorizedAtUtc': '2026-11-10T10:00:00+00:00'}
    return auth, phrase, comment


def test_owner_account_exact_scope_digest_and_publication_time_are_bound():
    auth, phrase, comment = sample()
    check_owner_comment(auth, phrase, comment)
    for bad in ({**comment, 'user': {'login': 'another-account', 'id': 42}},
                {**comment, 'body': phrase + ' changed'},
                {**comment, 'issue_url': 'https://api.github.com/repos/another/repo/issues/292'}):
        with pytest.raises(ValueError, match='PROVENANCE_INVALID'):
            check_owner_comment(auth, phrase, bad)
    with pytest.raises(ValueError, match='PROVENANCE_INVALID'):
        check_owner_comment(auth, 'APPROVE ANOTHER_SCOPE', comment)
    with pytest.raises(ValueError, match='TIME_MUST_MATCH_PUBLIC'):
        check_owner_comment({**auth, 'authorizedAtUtc': '2026-11-09T10:00:00Z'}, phrase, comment)
