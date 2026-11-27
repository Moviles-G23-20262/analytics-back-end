from .models import ExchangeStatus, MaterialStatus

UNSPECIFIED_LABEL = 'Unspecified'


def _clean_label(raw):
    text = ' '.join((raw or '').strip().split())
    return text if text else UNSPECIFIED_LABEL


def _new_bucket(label, faculty=None):
    return {
        'name': label,
        'faculty': faculty,
        'users': set(),
        'active_sellers': set(),
        'listings': 0,
        'buyer_inquiries': 0,
        'completed_exchanges': 0,
    }


def _serialize_bucket(bucket, include_faculty=False):
    listings = bucket['listings']
    completed = bucket['completed_exchanges']
    row = {
        'name': bucket['name'],
        'users': len(bucket['users']),
        'active_sellers': len(bucket['active_sellers']),
        'listings': listings,
        'buyer_inquiries': bucket['buyer_inquiries'],
        'completed_exchanges': completed,
        'conversion_rate': round(completed / listings, 4) if listings else 0.0,
    }
    if include_faculty:
        row['faculty'] = bucket['faculty'] or UNSPECIFIED_LABEL
    return row


def _sort_key(row):
    return (-row['completed_exchanges'], -row['listings'], -row['buyer_inquiries'], row['name'].lower())


def summarize_major_activity(users, listings, chat_rooms, exchanges):
    """BQ 18: Campus supply & demand by university major and faculty.

    Groups real CampusSwap listings, buyer chat inquiries, and completed exchanges by
    each seller's academic major and faculty so the team can see which programs drive
    the highest marketplace adoption and where to focus campus outreach.
    """
    user_major_key = {}
    user_faculty_key = {}
    majors = {}
    faculties = {}

    def ensure_major(raw_major, raw_faculty):
        label = _clean_label(raw_major)
        key = label.casefold()
        fac_label = _clean_label(raw_faculty)
        if key not in majors:
            majors[key] = _new_bucket(label, faculty=fac_label)
        elif majors[key]['faculty'] == UNSPECIFIED_LABEL and fac_label != UNSPECIFIED_LABEL:
            majors[key]['faculty'] = fac_label
        return key

    def ensure_faculty(raw_faculty):
        label = _clean_label(raw_faculty)
        key = label.casefold()
        if key not in faculties:
            faculties[key] = _new_bucket(label)
        return key

    for user in users:
        uid = str(user['id'])
        m_key = ensure_major(user.get('major'), user.get('faculty'))
        f_key = ensure_faculty(user.get('faculty'))
        user_major_key[uid] = m_key
        user_faculty_key[uid] = f_key
        majors[m_key]['users'].add(uid)
        faculties[f_key]['users'].add(uid)

    listing_seller = {}
    completed_materials = set()
    for ex in exchanges:
        if ex.get('status') == ExchangeStatus.COMPLETED:
            completed_materials.add(str(ex['material_id']))

    listings_total = 0
    completed_total = 0
    for item in listings:
        listings_total += 1
        mid = str(item['id'])
        sid = str(item['seller_id'])
        listing_seller[mid] = sid
        m_key = user_major_key.get(sid) or ensure_major(None, None)
        f_key = user_faculty_key.get(sid) or ensure_faculty(None)

        majors[m_key]['active_sellers'].add(sid)
        majors[m_key]['listings'] += 1
        faculties[f_key]['active_sellers'].add(sid)
        faculties[f_key]['listings'] += 1

        if mid in completed_materials or item.get('status') == MaterialStatus.SOLD:
            completed_total += 1
            majors[m_key]['completed_exchanges'] += 1
            faculties[f_key]['completed_exchanges'] += 1

    inquiries_total = 0
    for room in chat_rooms:
        inquiries_total += 1
        sid = str(room.get('seller_id') or listing_seller.get(str(room.get('material_id')), ''))
        m_key = user_major_key.get(sid) or ensure_major(None, None)
        f_key = user_faculty_key.get(sid) or ensure_faculty(None)
        majors[m_key]['buyer_inquiries'] += 1
        faculties[f_key]['buyer_inquiries'] += 1

    by_major = sorted(
        (_serialize_bucket(b, include_faculty=True) for b in majors.values()),
        key=_sort_key,
    )
    by_faculty = sorted(
        (_serialize_bucket(b, include_faculty=False) for b in faculties.values()),
        key=_sort_key,
    )

    return {
        'users_total': len(user_major_key),
        'listings_total': listings_total,
        'inquiries_total': inquiries_total,
        'completed_exchanges_total': completed_total,
        'majors_active': sum(1 for row in by_major if row['listings'] > 0 or row['buyer_inquiries'] > 0),
        'faculties_active': sum(1 for row in by_faculty if row['listings'] > 0 or row['buyer_inquiries'] > 0),
        'by_major': by_major,
        'by_faculty': by_faculty,
    }
