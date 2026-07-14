#!/usr/bin/env python3
"""Phase C: Seed TripAdvisor-style reviews with sub-ratings, realistic text, and helpfulness votes.

Uses raw psycopg2 to avoid SQLAlchemy text() binding complications.
"""

import json
import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2

DB_URL = "postgresql://athar:athar_pass@localhost:5432/athar_db"

REVIEW_TEMPLATES = {
    "historical": {
        "sub_labels": ["preservation", "information", "atmosphere", "value"],
        "templates": [
            ("Fascinating piece of history. The site is well maintained and the information boards are very helpful.", 4.5),
            ("Impressive ruins but could use better signage. A must-see if you're in the area.", 4.0),
            ("A hidden gem! Not crowded at all when we visited. The guide was knowledgeable.", 5.0),
            ("Interesting history but the site needs some restoration work. Still worth a visit.", 3.5),
            ("Disappointing. Expected more given the reviews. Many areas were inaccessible.", 2.5),
            ("Absolutely stunning! The preservation work here is remarkable. Highly recommend the guided tour.", 5.0),
            ("Nice place to spend an afternoon. The setting is beautiful and very photogenic.", 4.0),
            ("Remarkable historical significance. You can feel the history as you walk through.", 4.5),
            ("Good but overpriced entry fee. The site itself is interesting for about an hour.", 3.0),
            ("Exceptional archaeological site. One of the best preserved in the region.", 5.0),
        ],
    },
    "natural": {
        "sub_labels": ["scenery", "accessibility", "cleanliness", "value"],
        "templates": [
            ("Breathtaking views! The hike is moderate but absolutely worth it.", 5.0),
            ("Nature at its finest. Clean, well-marked trails, and stunning vistas.", 5.0),
            ("Beautiful landscape but the road to get there is rough. Come prepared.", 4.0),
            ("Peaceful and unspoiled. Not many tourists which was a nice change.", 4.5),
            ("The scenery is spectacular but there are no facilities nearby.", 3.5),
            ("Perfect for a day trip. Pack a picnic and enjoy the serene environment.", 4.5),
            ("We saw incredible wildlife here. The ecosystem is remarkably diverse.", 5.0),
            ("Nice but nothing extraordinary compared to other spots in Algeria.", 3.0),
            ("Stunning natural beauty. The colors at sunset are unforgettable.", 5.0),
            ("Could be amazing with better maintenance. Some trails were overgrown.", 3.0),
        ],
    },
    "cultural": {
        "sub_labels": ["authenticity", "experience", "value", "accessibility"],
        "templates": [
            ("A wonderful cultural experience. The locals were warm and welcoming.", 5.0),
            ("Great introduction to Algerian culture. The demonstrations were very informative.", 4.5),
            ("Unique experience! Learned so much about local traditions and crafts.", 5.0),
            ("Interesting but somewhat touristy. Still enjoyed the cultural showcase.", 3.5),
            ("Beautiful traditional architecture and friendly artisans. Bought some lovely crafts.", 4.5),
            ("The cultural show was fantastic! Really authentic performances.", 5.0),
            ("Good experience overall but the guided portion felt rushed.", 3.5),
            ("Deeply moving cultural site. The history here is palpable.", 4.5),
            ("A bit commercialized but the underlying culture shines through.", 3.0),
            ("Outstanding! Every traveler to Algeria should experience this.", 5.0),
        ],
    },
    "religious": {
        "sub_labels": ["atmosphere", "architecture", "respect", "accessibility"],
        "templates": [
            ("A place of profound peace and beautiful architecture. Respectful dress required.", 4.5),
            ("Stunning mosque with intricate details. Non-Muslims can visit at certain times.", 4.0),
            ("Spiritually uplifting. The call to prayer here gives you chills.", 5.0),
            ("Beautiful but very crowded during prayer times. Go early morning.", 4.0),
            ("The tile work and calligraphy are breathtaking. A masterpiece of Islamic art.", 5.0),
            ("Modest and serene atmosphere. A wonderful place for reflection.", 4.5),
            ("Impressive structure but limited access for non-worshippers.", 3.5),
            ("One of the most beautiful religious sites I've ever visited.", 5.0),
            ("Historic and well preserved. The guide explained the significance beautifully.", 4.5),
            ("Peaceful garden setting. The architecture blends tradition with tranquility.", 4.0),
        ],
    },
    "museum": {
        "sub_labels": ["exhibits", "layout", "information", "value"],
        "templates": [
            ("Excellent museum with well-curated exhibits. The collection is impressive.", 5.0),
            ("Fascinating artifacts but the lighting could be better for viewing.", 4.0),
            ("World-class museum hiding in Algeria. The mosaic collection is outstanding.", 5.0),
            ("Informative but small. You can see everything in about an hour.", 3.5),
            ("The guided tour brought the exhibits to life. Highly recommended.", 4.5),
            ("Disappointing. Many exhibits had no English descriptions.", 2.5),
            ("A treasure trove of history! The staff were very knowledgeable.", 5.0),
            ("Well organized and clean. Good for families with children.", 4.0),
            ("Impressive collection of artifacts spanning thousands of years.", 4.5),
            ("Needs modernization. Interactive exhibits would greatly improve the experience.", 3.0),
        ],
    },
    "beach": {
        "sub_labels": ["cleanliness", "water_quality", "facilities", "value"],
        "templates": [
            ("Crystal clear water and soft sand. One of the best beaches in Algeria!", 5.0),
            ("Beautiful beach but gets very crowded on weekends. Go during the week.", 4.0),
            ("Perfect spot for swimming. The water is calm and clear.", 4.5),
            ("Nice beach but lacking basic facilities like showers and toilets.", 3.0),
            ("Stunning coastline! Great for snorkeling and beachcombing.", 4.5),
            ("Family-friendly beach with gentle waves. Kids loved it.", 4.0),
            ("Clean and well-maintained. The nearby cafes are convenient.", 4.5),
            ("A bit rocky in some areas but overall a beautiful Mediterranean beach.", 3.5),
            ("Paradise found! Turquoise water and golden sand. Simply perfect.", 5.0),
            ("Good beach for a quick swim but not worth a long trip.", 3.0),
        ],
    },
    "mountain": {
        "sub_labels": ["trails", "scenery", "difficulty", "value"],
        "templates": [
            ("Challenging but rewarding hike. The summit views are incredible.", 5.0),
            ("Great mountain escape from the city heat. Much cooler up here.", 4.5),
            ("Well-marked trails suitable for intermediate hikers. Bring plenty of water.", 4.0),
            ("The landscape is dramatic and beautiful. A photographer's dream.", 5.0),
            ("Trail was more difficult than expected but the views made it worth it.", 3.5),
            ("Breathtaking alpine scenery. Reminded me of the European Alps.", 5.0),
            ("Beautiful but some trails were poorly maintained. Need better signage.", 3.0),
            ("Perfect weekend getaway. The fresh air and scenery are rejuvenating.", 4.5),
            ("Stunning panoramic views at the summit. Definitely worth the climb.", 4.5),
            ("Good for experienced hikers. Not recommended for beginners.", 3.5),
        ],
    },
    "park": {
        "sub_labels": ["maintenance", "facilities", "atmosphere", "value"],
        "templates": [
            ("Lovely park for a relaxing afternoon. Well maintained and clean.", 4.5),
            ("Great for families. The playground areas are well equipped.", 4.0),
            ("Beautiful green space in the heart of the city. A peaceful oasis.", 5.0),
            ("Nice but could use more benches and shade areas.", 3.5),
            ("Perfect for jogging and morning walks. Well lit paths.", 4.5),
            ("The botanical section is educational and beautiful. Loved it.", 4.0),
            ("A bit neglected in parts but the main areas are well kept.", 3.0),
            ("Lovely fountain and garden area. Great photo opportunities.", 4.0),
            ("Excellent park with facilities for all ages. Highly recommended.", 4.5),
            ("Peaceful and serene. Good place to read or meditate.", 4.5),
        ],
    },
    "market": {
        "sub_labels": ["variety", "prices", "authenticity", "atmosphere"],
        "templates": [
            ("Vibrant market with everything from spices to crafts. Bargain hard!", 4.5),
            ("Great place to buy souvenirs. Much cheaper than tourist shops.", 4.0),
            ("Overwhelming at first but you get used to the wonderful chaos.", 4.5),
            ("The fresh produce section is incredible. So many local varieties.", 5.0),
            ("Tourist prices in some stalls. Walk around before buying.", 3.0),
            ("An authentic Algerian market experience. The smells and sounds are unforgettable.", 5.0),
            ("Good selection but quality varies greatly between vendors.", 3.5),
            ("Perfect for foodies. The spice market alone is worth the visit.", 4.5),
            ("Crowded and chaotic but that's part of the charm.", 4.0),
            ("Best place to sample local street food. The grilled meats are amazing.", 4.5),
        ],
    },
    "restaurant": {
        "sub_labels": ["food_quality", "service", "ambiance", "value"],
        "templates": [
            ("Excellent couscous! The lamb was perfectly cooked. Friendly staff.", 5.0),
            ("Good traditional Algerian food at reasonable prices. Portions are generous.", 4.0),
            ("The best seafood in the region. Fresh and beautifully presented.", 5.0),
            ("Decent food but service was slow. Waited 40 minutes for our order.", 3.0),
            ("Delicious pastries and great coffee. Perfect for breakfast.", 4.5),
            ("Authentic home-style cooking. The owner treated us like family.", 5.0),
            ("Nice ambiance but the food was average. Expected more given the ratings.", 3.0),
            ("Incredible flavors! The spice blend in the tagine was perfect.", 4.5),
            ("Clean restaurant with good hygiene standards. Menu has English translations.", 4.0),
            ("Overpriced for what it is. There are better options nearby.", 2.5),
        ],
    },
    "cafe": {
        "sub_labels": ["coffee_quality", "atmosphere", "service", "value"],
        "templates": [
            ("Best mint tea in the city! The terrace has amazing views.", 5.0),
            ("Cozy atmosphere perfect for reading or working. Good Wi-Fi.", 4.5),
            ("Great coffee and pastries. A bit pricey but worth it.", 4.0),
            ("Traditional Algerian cafe with a modern twist. Love the decor.", 4.5),
            ("Disappointing coffee. Tasted burnt and the service was slow.", 2.5),
            ("Perfect spot for people watching. Sit outside and enjoy the buzz.", 4.0),
            ("Excellent chai and the staff are very friendly. Regular haunt now.", 5.0),
            ("Nice place but smoking inside makes it uncomfortable.", 3.0),
            ("Beautiful traditional setting with low tables and cushions. Very authentic.", 4.5),
            ("Good value cafe with consistent quality. My go-to spot.", 4.0),
        ],
    },
    "other": {
        "sub_labels": ["experience", "value", "accessibility", "atmosphere"],
        "templates": [
            ("Interesting experience! Not what I expected but enjoyable.", 4.0),
            ("Decent attraction but nothing special. Worth a quick visit.", 3.0),
            ("Great addition to any itinerary. Unique and memorable.", 4.5),
            ("Disappointing. The photos online look much better than reality.", 2.5),
            ("Really enjoyed this. Would recommend to anyone visiting the area.", 4.5),
            ("Average at best. Could be improved with better management.", 3.0),
            ("A fun surprise! Didn't expect much but ended up loving it.", 4.5),
            ("Good for a quick stop but not a destination in itself.", 3.0),
            ("Excellent experience for the price. Well worth the visit.", 4.5),
            ("Mixed feelings. Has potential but needs some work.", 3.0),
        ],
    },
}

ALGERIAN_FIRST_NAMES = [
    "Amir", "Yasmine", "Karim", "Nadia", "Mohamed", "Fatima", "Rachid", "Sofia",
    "Ahmed", "Leila", "Hakim", "Samira", "Omar", "Djamila", "Ali", "Zahra",
    "Brahim", "Malika", "Farid", "Nora", "Said", "Houria", "Djamel", "Salima",
    "Abdel", "Rym", "Tahar", "Khadija", "Nabil", "Meriem", "Sofiane", "Warda",
    "Yazid", "Amel", "Redouane", "Lydia", "Fouad", "Nassima", "Tariq", "Jasmine",
]

ALGERIAN_LAST_NAMES = [
    "Bensalem", "Makhloufi", "Kaci", "Mansouri", "Slimani", "Bouaziz",
    "Ait Ahmed", "Bouziane", "Cherif", "Messaoudi", "Khelifi", "Belkacem",
    "Benali", "Toumi", "Rahal", "Benammar", "Zidane", "Bellaoui",
    "Belaid", "Kara", "Hadjadj", "Mokhtar", "Ammari", "Zerrouki",
    "Djelloul", "Hamdi", "Mourad", "Sahraoui", "Ouali", "Ferhat",
]


def generate_review(category):
    entry = REVIEW_TEMPLATES.get(category, REVIEW_TEMPLATES["other"])
    txt, base_score = random.choice(entry["templates"])
    labels = entry["sub_labels"]
    overall = max(1.0, min(5.0, round(base_score + random.uniform(-0.5, 0.5), 1)))
    sub_scores = [max(1.0, min(5.0, round(base_score + random.uniform(-1.0, 1.0), 1))) for _ in labels]
    return txt, overall, dict(zip(labels, sub_scores))


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id, category, wilaya_id, is_featured FROM pois ORDER BY is_featured DESC, wilaya_id")
    pois = cur.fetchall()
    print(f"Total POIs: {len(pois)}")

    cur.execute("SELECT id FROM users")
    user_ids = [str(r[0]) for r in cur.fetchall()]
    print(f"Existing users: {len(user_ids)}")

    # Create more synthetic users for diversity
    users_to_create = max(0, 25 - len(user_ids))
    for _ in range(users_to_create):
        first = random.choice(ALGERIAN_FIRST_NAMES)
        last = random.choice(ALGERIAN_LAST_NAMES)
        phone = f"+213{random.randint(500000000, 799999999)}"
        cur.execute(
            "INSERT INTO users (id, phone, role, language, is_active, is_verified, display_name, created_at, updated_at) "
            "VALUES (%s, %s, 'traveler', 'en', true, true, %s, NOW(), NOW()) ON CONFLICT (phone) DO NOTHING",
            (str(uuid.uuid4()), phone, f"{first} {last}"),
        )
    conn.commit()

    cur.execute("SELECT id FROM users")
    user_ids = [str(r[0]) for r in cur.fetchall()]
    print(f"Total users: {len(user_ids)}")

    cur.execute("SELECT COUNT(*) FROM reviews")
    existing = cur.fetchone()[0]
    print(f"Existing reviews: {existing}")
    if existing > 0:
        cur.execute("DELETE FROM review_votes")
        cur.execute("DELETE FROM reviews")
        conn.commit()
        print("Cleared existing reviews")

    featured = [p for p in pois if p[3]]
    non_featured = [p for p in pois if not p[3]]
    target = min(3000, len(pois))
    review_pois = list(featured)
    if len(review_pois) < target:
        random.shuffle(non_featured)
        review_pois.extend(non_featured[:target - len(review_pois)])
    random.shuffle(review_pois)
    print(f"Targeting {len(review_pois)} POIs for reviews")

    vote_data = []

    for idx, poi_row in enumerate(review_pois):
        poi_id, category, wilaya_id, is_featured = poi_row
        num_reviews = min(12, max(1, random.randint(3, 8) + (2 if is_featured else 0)))
        reviewers = random.sample(user_ids, min(num_reviews + 2, len(user_ids)))

        for reviewer_id in reviewers[:num_reviews]:
            txt, overall, sub_ratings = generate_review(category)
            days_ago = random.randint(1, 180)
            created = datetime.now(timezone.utc) - timedelta(days=days_ago)
            rid = uuid.uuid4()
            is_verified = random.random() < 0.4

            cur.execute(
                "INSERT INTO reviews (id, user_id, poi_id, overall_score, text, sub_ratings, is_verified, helpfulness_count, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, 0, %s, %s) "
                "ON CONFLICT (user_id, poi_id) DO UPDATE SET "
                "overall_score = EXCLUDED.overall_score, text = EXCLUDED.text, "
                "sub_ratings = EXCLUDED.sub_ratings, is_verified = EXCLUDED.is_verified",
                (str(rid), str(reviewer_id), str(poi_id), overall, txt, json.dumps(sub_ratings), is_verified, created, created),
            )

            if random.random() < 0.6:
                voters = [u for u in user_ids if u != str(reviewer_id)]
                random.shuffle(voters)
                for voter_id in voters[:random.randint(1, 6)]:
                    vote_data.append((rid, voter_id, random.random() < 0.8))

        if (idx + 1) % 500 == 0:
            conn.commit()
            print(f"  {idx + 1}/{len(review_pois)} POIs processed...")

    conn.commit()
    print(f"All reviews inserted. Inserting {len(vote_data)} votes...")

    for i, (rid, uid, helpful) in enumerate(vote_data):
        cur.execute(
            "INSERT INTO review_votes (id, user_id, review_id, helpful, created_at) "
            "VALUES (%s, %s, %s, %s, NOW()) ON CONFLICT (user_id, review_id) DO NOTHING",
            (str(uuid.uuid4()), uid, str(rid), helpful),
        )
        if (i + 1) % 1000 == 0:
            conn.commit()
            print(f"  Votes: {i + 1}/{len(vote_data)}")

    conn.commit()

    cur.execute("""
        UPDATE reviews r
        SET helpfulness_count = (
            SELECT COUNT(*) FROM review_votes rv
            WHERE rv.review_id = r.id AND rv.helpful = true
        )
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM reviews")
    final = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM review_votes")
    votes = cur.fetchone()[0]
    print(f"\nDone! {final} reviews, {votes} votes across {len(review_pois)} POIs.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
