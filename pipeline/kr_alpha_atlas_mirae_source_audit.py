"""Source-only diagnostics and coverage propagation; no alpha/outcome entry."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pipeline import kr_alpha_atlas_readiness as RD
from pipeline import kr_alpha_atlas_price_integrity as P
from pipeline import kr_industry_anatomy_execution as IE
from pipeline.kr_alpha_atlas_phase_c import contract
from pipeline import kr_alpha_atlas_mirae_repair as R

FEATURES = ('H01_industryRelMom126', 'H08_equalVsCapWeightIndustry')


def source_diagnostic(root=contract.ROOT):
    q = R.read_correction(root)
    R.verify_raw_quotes(root, q)
    frame = R.reconstruct(q)
    raw, legacy, _, lineage = P.pinned_sample(root, {
        'sourceCommit':q['sourceCommit'], 'securities':[{'ticker':R.TICKER}],
        'sourceWindows':[{'start':'2018-01-22','end':'2018-01-24'},
                         {'start':'2026-03-13','end':'2026-03-17'}],
    })
    raw, legacy = raw[R.TICKER], legacy[R.TICKER]

    def scale_step(before, after):
        return {k:(legacy[after][k.title()]/raw[after][k]) /
                  (legacy[before][k.title()]/raw[before][k])
                for k in ('open','high','low','close')}

    rights_steps = scale_step('2018-01-22','2018-01-23')
    dividend_steps = scale_step('2026-03-13','2026-03-16')
    previous_raw = raw['2026-03-13']['close']
    registered_cash = q['stockDividendEvent']['cashKrwPerCommonShare']
    share = 1 + q['stockDividendEvent']['commonSharesPerCommonShare']
    factors, units, previous = 1.0, 1.0, None
    residuals = []
    events = {r['date']: r for r in q['registeredPartialEvents']}
    for row in q['rawQuotes']:
        d = row['date']
        if d in q['quarantinedSessions']:
            factors, units = 1.0, 1.0
            assert frame.loc[d, ['Open','High','Low','Close']].isna().all()
        else:
            event = events.get(d, {})
            cash, ratio = float(event.get('dividend') or 0), float(event.get('split') or 1)
            if d == '2026-03-16':
                cash, ratio = 300.0, 1.0073206
            if cash:
                factors /= 1-cash/previous
            factors *= ratio
            units *= ratio
            for k in ('open','high','low','close'):
                residuals.append(abs(frame.loc[d,k.title()]/factors-row[k]))
            residuals.append(abs(frame.loc[d,'Volume']*units-row['volume']))
        previous = row['close']
    return {
        'scope':'006800_SOURCE_ONLY_SAME_SESSION_ALL_OHLCV_AND_CORPORATE_ACTIONS',
        'sourceRows':len(frame),'positiveRawOhlcvRows':len(frame),
        'rawKrxSourceIdentity':q['rawQuoteIdentity'],
        'sourceManifest':q['newSourceManifest'],
        'sourceManifestSha256':contract.file_hash(Path(root)/q['newSourceManifest']),
        'correctionFileSha256':contract.file_hash(Path(root)/R.CORRECTION),
        'originalReplayEventWindowIdentities':lineage,
        'sameSessionRawQuoteReverseTransformMaxAbsUnits':max(residuals),
        'event2018':{
            **q['rightsEvent'],
            'firstUnregisteredQuoteScaleChange':'2018-01-23',
            'originalQuoteScaleStep':rights_steps['close'],
            'originalAllOhlcQuoteScaleSteps':rights_steps,
            'rawKrxBeforeAfter':{d:raw[d] for d in ['2018-01-22','2018-01-23','2018-01-24']},
            'priorReportLargestResidualDate':'2018-03-28',
            'rootCause':'Cross-class preferred subscription-right ex date omitted from the split/cash registry; vendor quotation adjustment is not a verified right payout. March 28 is a residual maximum, not an inferred event date.',
            'status':'KNOWN_EVENT_UNVALUED_RIGHTS_BOUNDARY_QUARANTINED',
        },
        'event2026':{
            **q['stockDividendEvent'],
            'previousRawKrxCloseKrw':previous_raw,
            'singleRegisteredCashFactor':1/(1-registered_cash/previous_raw),
            'originalInternalQuoteScaleStep':dividend_steps['close'],
            'originalAllOhlcQuoteScaleSteps':dividend_steps,
            'rawKrxBeforeAfter':{d:raw[d] for d in ['2026-03-13','2026-03-16','2026-03-17']},
            'correctedPartialIndexFactor':share/(1-registered_cash/previous_raw),
            'rootCause':'Vendor quote already applies cash factor. Shared adjuster applies cash again and assumes vendor stock-entitlement adjustment; that assumption is false here. Raw KRX reconstruction applies cash once and the distinct common-stock entitlement once, never a cash factor to share-volume units.',
            'status':'SOURCE_RECONSTRUCTED_WITH_SEPARATE_CASH_AND_COMMON_SHARE_ENTITLEMENT',
            'cashPaymentDate':'NOT_INDEPENDENTLY_VERIFIED_NOT_REQUIRED_FOR_FROZEN_EX_DATE_INDEX_CONVENTION',
            'stockDeliveryEvidence':'Official KRX listing on 2026-04-22; issuance date 2026-03-24.',
        },
        'basisStatus':'VERIFIED_CONNECTED_RAW_PRICE_SEGMENTS_NOT_A_CONTIGUOUS_VERIFIED_RIGHTS_WEALTH_PATH',
        'quarantinedSessions':list(R.QUARANTINE),
        'noMarketPriceChangeFittedAdjustment':True,
        'originalPartialDistributionAndVendorVintageLimitationsRetained':True,
        'realHistoricalAlphaOutcomeReads':0,'realForwardLabels':0,'realHistoricalModelFits':0,
        'realPortfolioBacktests':0,'formalExecutionDispatches':0,'permanentExecutionLocksCreated':0,
    }


def _counts(rows, mask):
    part = rows.loc[mask]
    return {'nameDateObservations':int(mask.sum()),'securities':int(part.ticker.nunique()),
            'signalDates':int(part.date.nunique()),
            'firstSignal':part.date.min() if len(part) else None,
            'lastSignal':part.date.max() if len(part) else None,
            'byYear':{str(k):int(v) for k,v in part.groupby(part.date.str[:4]).size().items()},
            'byIndustry':{str(k):int(v) for k,v in part.groupby('industry').size().items()}}


def coverage_propagation(data, capture):
    """Reproduce legacy *availability*, never forward performance.

    The only changed industry constituent is Mirae. Original trailing numeric
    helpers/cohort construction are reused for its FINANCIALS cohort. Every
    non-financial availability bit must agree with the frozen reference counts.
    """
    inputs, legacy = capture['inputs'], capture['legacyMirae']
    rows = data.rows
    membership = rows[['date','ticker','industry','industryMembershipStatus']].rename(columns={'industryMembershipStatus':'membershipStatus'})
    cohorts = IE.I.build_cohorts(membership, rows[['date','ticker','marketCap']])
    old_prices = {**inputs.prices, R.TICKER:legacy}
    repaired = data.values[FEATURES[1]].notna()
    original, blocked = repaired.copy(), repaired.copy()
    financial = rows.industry.eq('FINANCIALS')
    original.loc[financial] = False
    blocked.loc[financial] = False
    for (date, industry), cohort in cohorts.items():
        if industry!='FINANCIALS' or cohort['status']!='ELIGIBLE' or cohort['capWeights'] is None:
            continue
        past = IE.past_features(old_prices,cohort['members'],inputs.calendar,date)
        valid = all(np.isfinite(past[t]['trail126']) for t in cohort['members'])
        if valid:
            original.loc[(rows.date==date)&financial] = True
    reference = json.loads((contract.ROOT/'docs/results/kr-alpha-atlas-phase-b-readiness.json').read_text())
    parent = json.loads((contract.ROOT/'docs/audits/kr-alpha-atlas-phase-c-integrity/corrected-full-input-preflight.json').read_text())
    comparison = {}
    for feature in FEATURES:
        proposed = data.values[feature].notna()
        if not proposed.equals(repaired):
            raise ValueError('H01_H08_AVAILABILITY_DIFFERENT_REQUIRES_INSPECTION')
        # No unexplained global or unrelated-industry mask may be introduced.
        if int(original.sum()) != reference['features'][feature]['measuredObservations']:
            raise ValueError('LEGACY_SOURCE_COVERAGE_NOT_REPRODUCED')
        expected_parent = (parent['correctedSourceReadiness']['eligibleFeatureCoverage'].get(feature) or
                           parent['correctedSourceReadiness']['baselines']['B0_MARKET_INDUSTRY_PRICE_REFERENCE'])
        if feature==FEATURES[1] and int(blocked.sum())!=expected_parent['measuredObservations']:
            raise ValueError('PUBLISHED_V2_COVERAGE_NOT_REPRODUCED')
        first = reference['features'][feature]['earliestUsableSignalDate']
        last = reference['features'][feature]['latestUsableSignalDate']
        common = rows.date.between(first,last)
        comparison[feature] = {
            'unchangedUsableRange':[first,last],'commonDenominator':int(common.sum()),
            'originalPhaseBMeasuredRows':int(original.sum()),
            'originalPhaseBUsableRangeCoveragePct':reference['features'][feature]['coverageWithinUsableRangePct'],
            'publishedBlockedV2MeasuredRows':int(blocked.sum()),
            'publishedBlockedV2UsableRangeCoveragePct':float(blocked[common].mean()*100),
            'sourceRepairedMeasuredRows':int(proposed.sum()),
            'sourceRepairedUsableRangeCoveragePct':float(proposed[common].mean()*100),
            'originalCoverageFloorPct':100*RD.MIN_FEATURE_COVERAGE,
            'originalToBlockedLost':_counts(rows, original&~blocked),
            'blockedToRepairedRestored':_counts(rows, proposed&~blocked),
            'originalToRepairedLost':_counts(rows, original&~proposed),
            'unrelatedIndustriesAdditionalMissingRows':int((original&~proposed&~financial).sum()),
            'reasons':{'direct':'NON_FINITE_PRICE_IN_WINDOW',
                       'peerIndustry':'INDUSTRY_COHORT_MEMBER_MISSING_INPUT',
                       'boundary':'2018-01-23 unvalued preferred subscription right; no endpoint bridge'},
        }
    return {'dependencyChain':'006800 source boundary -> every constituent required by original cap/equal industry definition -> H01/H08 -> B0/B4 -> X3',
            'allMemberRuleRequiredByOriginalDefinition':True,
            'noSurvivorRenormalizationOrChangedIndustryMembership':True,
            'comparisons':comparison,
            'newDirectSecurityPriceRows':int(rows.ticker.eq(R.TICKER).sum()),
            'originalThresholdsUnchanged':True,'stockOutcomeWindowsConstructed':0}
