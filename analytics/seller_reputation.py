from .models import MaterialStatus

REPUTATION_STAR_GROUPS = (
    ('no_reviews', 'No reviews yet'),
    ('below_3', 'Below 3 stars'),
    ('3_to_4', '3 to 4 stars'),
    ('4_to_4_5', '4 to 4.5 stars'),
    ('4_5_and_up', '4.5 stars and up'),
)
REPUTATION_REVIEW_GROUPS = (
    ('none', 'No reviews'),
    ('1_2', '1 or 2 reviews'),
    ('3_5', '3 to 5 reviews'),
    ('6_plus', '6 or more reviews'),
)


def _star_group(average):
    if average is None:
        return 'no_reviews'
    if average < 3:
        return 'below_3'
    if average < 4:
        return '3_to_4'
    if average < 4.5:
        return '4_to_4_5'
    return '4_5_and_up'


def _review_group(count):
    if count == 0:
        return 'none'
    if count <= 2:
        return '1_2'
    if count <= 5:
        return '3_5'
    return '6_plus'


def _median(sorted_values):
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2


def _new_reputation_group():
    return {'sellers': set(), 'listings': 0, 'contacted': 0, 'buyers': 0, 'sold': 0, 'days_to_sell': []}


def _reputation_row(key, label, group):
    listings = group['listings']
    days = sorted(group['days_to_sell'])
    return {
        'group': key,
        'label': label,
        'sellers': len(group['sellers']),
        'listings': listings,
        'contacted': group['contacted'],
        'contact_rate': round(group['contacted'] / listings, 4) if listings else 0.0,
        'buyers_per_listing': round(group['buyers'] / listings, 2) if listings else 0.0,
        'sold': group['sold'],
        'sale_rate': round(group['sold'] / listings, 4) if listings else 0.0,
        'median_days_to_sell': round(_median(days), 1) if days else None,
    }


def summarize_seller_reputation(listings, completed_at, ratings, contacts):
    # estrellas recibidas por vendedor y compradores distintos que abrieron chat por publicación
    stars = {}
    for rating in ratings:
        stars.setdefault(str(rating['rated_id']), []).append(rating['stars'])
    buyers = {}
    for contact in contacts:
        buyers.setdefault(str(contact['material_id']), set()).add(str(contact['buyer_id']))
    completed_at = {str(k): v for k, v in completed_at.items()}

    by_stars = {key: _new_reputation_group() for key, _ in REPUTATION_STAR_GROUPS}
    by_reviews = {key: _new_reputation_group() for key, _ in REPUTATION_REVIEW_GROUPS}
    total = 0

    for listing in listings:
        total += 1
        seller = str(listing['seller_id'])
        received = stars.get(seller, [])
        average = sum(received) / len(received) if received else None
        interested = len(buyers.get(str(listing['id']), ()))
        done = completed_at.get(str(listing['id']))
        sold = done is not None or listing['status'] == MaterialStatus.SOLD

        for group in (by_stars[_star_group(average)], by_reviews[_review_group(len(received))]):
            group['sellers'].add(seller)
            group['listings'] += 1
            group['buyers'] += interested
            if interested:
                group['contacted'] += 1
            if sold:
                group['sold'] += 1
                if done and listing['created_at']:
                    group['days_to_sell'].append(max((done - listing['created_at']).total_seconds() / 86400, 0.0))

    return {
        'listings_total': total,
        'sellers_with_reviews': len(stars),
        'by_stars': [_reputation_row(key, label, by_stars[key]) for key, label in REPUTATION_STAR_GROUPS],
        'by_review_count': [_reputation_row(key, label, by_reviews[key]) for key, label in REPUTATION_REVIEW_GROUPS],
    }