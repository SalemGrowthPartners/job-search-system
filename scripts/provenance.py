"""Source observations and verification, independent of scoring and browser access."""
import copy
import hashlib
from datetime import date, datetime, timezone
from urllib.parse import urlsplit


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be an ISO datetime with timezone')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('timestamp must be an ISO datetime with timezone')
    if parsed.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def posting_date(value):
    if isinstance(value, str) and len(value) == 10:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('Invalid original posting date')
        return value
    return timestamp(value)


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + ' must be a nonempty string')
    return value.strip()


def validate(raw, canonical_url):
    p = copy.deepcopy(raw)
    if not isinstance(p, dict) or type(p.get('version')) is not int or p['version'] != 1:
        raise ValueError('provenance.version must be 1')
    origin = p.get('origin')
    if origin is not None:
        if not isinstance(origin, dict):
            raise ValueError('origin must be an object or null')
        for key in ('source_id', 'method', 'run_id'):
            origin[key] = text(origin.get(key), 'origin.' + key)
        origin['url'] = canonical_url(origin.get('url'))
        origin['at'] = timestamp(origin.get('at'))
        if origin.get('query_id') is not None:
            origin['query_id'] = text(origin['query_id'], 'query_id')
    observations = p.get('observations', [])
    if not isinstance(observations, list):
        raise ValueError('observations must be an array')
    for o in observations:
        if not isinstance(o, dict):
            raise ValueError('Each observation must be an object')
        for key in ('source_id', 'method', 'run_id'):
            o[key] = text(o.get(key), key)
        o['url'] = canonical_url(o.get('url'))
        o['at'] = timestamp(o.get('at'))
    if origin is not None and origin not in observations:
        observations.append(copy.deepcopy(origin))
    p['observations'] = observations
    p['origin'] = origin
    for key in ('authoritative_posting_url', 'application_url'):
        if p.get(key) is not None:
            p[key] = canonical_url(p[key])
    for key in ('source_published_at', 'source_updated_at'):
        if p.get(key) is not None:
            p[key] = timestamp(p[key])
    if p.get('date_basis', 'unknown') not in ('original_published', 'last_published', 'updated', 'unknown'):
        raise ValueError('Invalid date_basis')
    p.setdefault('date_basis', 'unknown')
    for key in ('employer_domain', 'ats_provider', 'ats_board_id', 'ats_posting_id'):
        if p.get(key) is not None:
            p[key] = text(p[key], key)
    if p.get('availability') not in ('open', 'closed', 'unverified', 'unavailable', 'evergreen'):
        raise ValueError('Invalid availability')
    if p.get('last_verified_at') is not None:
        p['last_verified_at'] = timestamp(p['last_verified_at'])
    if p['availability'] == 'open':
        for key in ('authoritative_posting_url', 'application_url', 'last_verified_at', 'verification_evidence', 'employer_domain'):
            text(p.get(key), key)
        if urlsplit('https://' + p['employer_domain']).hostname != p['employer_domain']:
            raise ValueError('employer_domain must be a hostname')
    if p.get('original_posted_at') is not None:
        p['original_posted_at'] = posting_date(p['original_posted_at'])
        evidence = p.get('original_posted_evidence')
        if not isinstance(evidence, dict) or evidence.get('date_type') != 'original_published':
            raise ValueError('Original posting date requires original-publication evidence')
        evidence['url'] = canonical_url(evidence.get('url'))
        evidence['raw_text'] = text(evidence.get('raw_text'), 'original posting raw_text')
        evidence['observed_at'] = timestamp(evidence.get('observed_at'))
        if p['original_posted_at'][:10] > evidence['observed_at'][:10]:
            raise ValueError('Original posting date cannot be later than its observation')
    if p.get('evergreen_checked_at') is not None:
        p['evergreen_checked_at'] = timestamp(p['evergreen_checked_at'])
        p['evergreen_check_evidence'] = text(p.get('evergreen_check_evidence'), 'evergreen_check_evidence')
    return p


def combine(old, new):
    """Never invent the origin of legacy data; keep all encounters on reimport."""
    if old is None:
        return copy.deepcopy(new)
    if new is None:
        return copy.deepcopy(old)
    result = copy.deepcopy(new)
    if old.get('original_posted_at') is not None:
        if new.get('original_posted_at') is not None and new['original_posted_at'] != old['original_posted_at']:
            raise ValueError('Original posting date conflict; reconcile evidence rather than resetting age')
        result['original_posted_at'] = old['original_posted_at']
        result['original_posted_evidence'] = copy.deepcopy(old['original_posted_evidence'])
    if old.get('evergreen_checked_at', '') > new.get('evergreen_checked_at', ''):
        result['evergreen_checked_at'] = old['evergreen_checked_at']
        result['evergreen_check_evidence'] = old['evergreen_check_evidence']
    result['origin'] = copy.deepcopy(old.get('origin'))
    result['origin_status'] = old.get('origin_status', 'recorded' if old.get('origin') else 'legacy_unknown')
    result['observations'] = copy.deepcopy(old.get('observations', []))
    for o in new.get('observations', []):
        if o not in result['observations']:
            result['observations'].append(copy.deepcopy(o))
    # A delayed/older observation cannot roll authoritative evidence backwards.
    if old.get('last_verified_at', '') > new.get('last_verified_at', ''):
        for key in ('authoritative_posting_url', 'application_url', 'last_verified_at', 'verification_evidence', 'availability', 'employer_domain', 'ats_provider', 'ats_board_id', 'ats_posting_id', 'source_published_at', 'source_updated_at', 'date_basis'):
            if key in old:
                result[key] = copy.deepcopy(old[key])
    return result


def legacy():
    return {'version': 1, 'origin': None, 'origin_status': 'legacy_unknown',
            'observations': [], 'availability': 'unverified', 'date_basis': 'unknown'}


def description_hash(description):
    return hashlib.sha256(description.encode()).hexdigest()
