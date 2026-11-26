# 기업 공시 전향 writer 인수 승인 패킷

설치와 writer 활성화는 별개다. #382의 설치에서는 `automation.enabled=false`를 유지한다. 설치 후 기본 수동 실행은 `status-only`이며 상태와 무결성을 읽기만 한다. GitHub Actions는 Claude 예약을 조회하거나 끌 권한이 없다.

## 소유자의 전환 절차

1. 활성 Claude 예약 `trig_013qoRYz6H9UwUosNzCWv69B`를 그 예약을 소유한 Claude 세션(`cse_01UtFTvgwN2oL1NjAAMWvwBg`) 또는 소유자 예약 관리 화면에서 비활성화한다. `get_trigger`로 동일 ID의 `enabled: false`를 다시 읽는다. 기존에 중지된 `trig_01XwJ7yivCe5uokkmUTk8MWE`도 [원래 세션](https://claude.ai/code/session_01UtFTvhsc62UJBfDJZ6qQZv)에서 같은 상태를 조회한다. 두 예약에 진행 중인 writer 실행이 없거나 종료됐는지 확인한다.
2. 두 결과의 정확한 ID, JSON 불리언 `enabled: false`, 실제 UTC 조회 시각과 실행 종료 확인을 전달한다. 비활성화 요청 자체, 실패 로그, 추정 시각은 증거로 사용하지 않는다. 레거시 writer를 영구 퇴역시킬 때만 전환을 승인한다.
3. 담당자가 아래 형식의 정확 바이트 파일을 준비하면 소유자가 [#292](https://github.com/jaehojung1879-netizen/Investment/issues/292)에 `PROSPECTIVE_WRITER_CUTOVER_V1 sha256=<파일 SHA-256>` 한 줄을 게시한다. 가드는 GitHub에서 해당 댓글을 새로 가져와 이슈, 저장소 소유자의 계정 ID, 바이트 해시와 승인 시각을 확인한다. 7일 제한은 **최초 인수 때 증거의 시효**에만 적용한다. 승인된 전환의 정기 재서명은 필요 없다. 승인 철회 시 댓글의 승인 줄을 제거하고 다음 운영 PR에서 `automation.enabled=false`를 기록한다.
4. 운영 담당자는 등록 고정 코드의 보존 태그를 확인한 뒤 정확한 승인 댓글 ID, 자동화 플래그 및 첫 운영 세션 직전의 모니터링 기준을 새 활성화 변경에 담는다. #382 자체로는 그 변경을 적용하지 않는다.

등록 파일 위치는 `research/prospective_ops/attestations/kr-corporate-information-events-v1-single-writer.json`이다. 아래 값은 입력 형식이며 실제 readback으로 교체할 때까지 승인 효력이 없다.

```json
{
  "schema": "PROSPECTIVE_WRITER_CUTOVER_V1",
  "studyId": "kr-corporate-information-events-v1",
  "pinnedCodeCommit": "8aee189ff453d9bd624a67df5e1e5975bd7d211c",
  "authorizationSha256": "c7191d7542a4e3b0d832e63625201585998632ef680d1976c0e2f0faab115d1e",
  "successor": {
    "repository": "jaehojung1879-netizen/Investment",
    "workflow": ".github/workflows/prospective-ops.yml",
    "ref": "refs/heads/main"
  },
  "attestedAtUtc": "<UTC>",
  "legacyRunsDrained": true,
  "retiredPermanently": true,
  "readbacks": [
    {"id": "trig_01XwJ7yivCe5uokkmUTk8MWE", "enabled": false, "readbackUtc": "<UTC>", "source": "CLAUDE_GET_TRIGGER_READBACK"},
    {"id": "trig_013qoRYz6H9UwUosNzCWv69B", "enabled": false, "readbackUtc": "<UTC>", "source": "CLAUDE_GET_TRIGGER_READBACK"}
  ]
}
```

## 고정 코드 보존

주석 태그 `pinned/kr-corporate-information-events-v1/8aee189`가 정확히 `8aee189ff453d9bd624a67df5e1e5975bd7d211c`를 가리키게 한다. 원격 태그 객체와 peel 대상, 등록 Git 트리 `b1cd5b1852c401a1a9c3a13fce8b1466a4f5e61e`를 대조한다. 같은 커밋이 main ancestry에 들어가도 보존 조건을 충족한다. 태그 발행을 위해 #322를 병합할 필요는 없다.

```bash
git fetch --no-tags origin 8aee189ff453d9bd624a67df5e1e5975bd7d211c
git tag -a pinned/kr-corporate-information-events-v1/8aee189 \
  8aee189ff453d9bd624a67df5e1e5975bd7d211c -m 'Preserve the registered corporate prospective writer'
git push origin refs/tags/pinned/kr-corporate-information-events-v1/8aee189
git ls-remote origin 'refs/tags/pinned/kr-corporate-information-events-v1/8aee189*'
```

## 설치 및 인수 검증

- 병합 총괄이 정확한 최신 main의 native Tests와 별도 비작성자 검토를 확인한 후 설치를 병합한다.
- 설치 직후 [Prospective ops](https://github.com/jaehojung1879-netizen/Investment/actions/workflows/prospective-ops.yml)에서 main / `status-only`로 상태 아티팩트와 기존 세 영수증의 무결성을 확인한다.
- 활성화가 별도로 승인된 뒤 다음 두 적격 거래일에 원격 `signal-history`의 새 세션 영수증 각각 한 건, 원 파일 앞부분의 10,191바이트와 승인·사양 해시 보존을 검증한다. 같은 세션 재시도 결과가 이미 기록된 영수증을 확인해야 한다.
- Claude 예약이 다시 켜졌거나 종료 증거가 무효라면 승인 댓글을 철회한다. Actions 직렬화와 Git 원격 충돌 검사는 외부 예약 관리 권한을 대체하지 않는다.
