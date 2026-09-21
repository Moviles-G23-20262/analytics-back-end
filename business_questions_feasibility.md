# Business Questions Feasibility Report

This document evaluates the 14 proposed business questions against our current database schema. Please review this before starting your implementation to ensure the data you need actually exists.

## Summary

* ✅ **Fully Possible:** 5, 6, 7, 8, 9, 10, 11

* ⚠️ **Partially Possible / Needs Workarounds:** 2, 3, 4, 13

* ❌ **Not Possible (Needs schema updates or 3rd party tools):** 1, 12, 14

## Detailed Breakdown

### ❌ 1. In which screens and features of the app do crashes happen most often, and on which OS versions and device models?

**Status:** Not Possible
**Reason:** Our database schema does not track crash logs, device OS, or hardware models. While the `AnalyticsEvent` table has a `metadata` JSON field, relying on this for crash analytics is an anti-pattern.
**Action:** We need to integrate a dedicated crash-reporting tool like Sentry or Firebase Crashlytics to answer this. Do not attempt to build this in Django.

### ⚠️ 2. How many listings does a buyer open before contacting a seller, and how many before completing an exchange?

**Status:** Partially Possible
**Reason:** We can track when a user opens a listing via `AnalyticsEvent` (`eventType = LISTING_VIEW`), contacts a seller (`CONTACT_SELLER` or `ChatRoom` creation), and completes a purchase (`Exchange`). However, linking a specific chain of "views" directly to a specific "contact" requires complex time-series queries (e.g., counting views by a `userId` leading up to the `ChatRoom.createdAt` timestamp).
**Action:** Implementable, but requires careful window functions or complex chronological filtering in your queries.

### ⚠️ 3. Which photos do sellers upload most (number of photos, angles, close-ups of damage), and how does that relate to the number of buyers who contact them?

**Status:** Partially Possible
**Reason:** We have `Material.imageUrls`, so we can count the **number** of photos by measuring the array length. We can easily relate this count to the number of associated `ChatRoom` records. However, the database cannot tell us what is *inside* the photos (angles, close-ups).
**Action:** You can implement the correlation between *photo count* and *contacts*. Evaluating image content (angles/damage) is impossible without an AI Computer Vision integration.

### ⚠️ 4. How many messages do a buyer and a seller exchange in the app chat before they agree on a meeting point, and how long this conversation take?

**Status:** Partially Possible
**Reason:** We can count total `Message` records inside a `ChatRoom` and measure the time between the first message and the `Exchange.completedAt` date. However, there is no flag or status for "agreed on meeting point."
**Action:** You must use the `Exchange` creation/completion as the proxy for "agreement." You cannot identify the exact message where they agreed on a location unless you attempt unreliable natural language processing on `Message.content`.

### ✅ 5. At what time of the day and which days of the week do students publish and browse the most?

**Status:** Fully Possible
**Reason:**

* **Publishing:** Extract day/hour from `Material.createdAt`.

* **Browsing:** Extract day/hour from `AnalyticsEvent.occurredAt` where `eventType` is `LISTING_VIEW` or `SEARCH`.
  **Action:** Safe to implement. Use standard SQL date/time extraction functions.

### ✅ 6. Which categories of items generate the most listings and the most completed exchanges?

**Status:** Fully Possible
**Reason:** `Material` has a `category` enum. You can `GROUP BY category` to count total materials, and do a `JOIN` with `Exchange` to count completed sales per category.
**Action:** Safe to implement.

### ✅ 7. How many buyers save items in the wishlist, and how many of those saved items end in a purchase after a Smart matching notification?

**Status:** Fully Possible
**Reason:** All required entities exist. You can query `WishlistItem` to count saves. You can then check if a `Notification` with `type = SMART_MATCH` exists for that `userId`/`materialId`, and check if an `Exchange` exists for the same combination.
**Action:** Safe to implement.

### ✅ 8. Which fields of the listing form do sellers leave empty most often (course, edition, condition, faculty)?

**Status:** Fully Possible
**Reason:** All referenced fields exist in the schema. We can check for nulls in `Material.courseCode`, `Material.edition`, and `Material.condition`. `Faculty` is tracked on the `User` model (`seller.faculty`).
**Action:** Safe to implement. You will just need to join the `Material` table to the `User` table to check the seller's faculty field.

### ✅ 9. How do prices of the same item vary (same book edition, same model) between sellers, faculties and item condition?

**Status:** Fully Possible
**Reason:** The database now tracks both `edition` and `model` directly on the `Material` table. We also have `condition` on `Material` and the seller's `faculty` via the `User` relation.
**Action:** Safe to implement. You can accurately group records by the exact `edition` or `model` string and aggregate the `price`, segmenting the results by `condition` and `seller.faculty`.

### ✅ 10. Which listings are published but never sold, how long do they stay active, and what do they have in common (price, category, photos, seller rating)?

**Status:** Fully Possible
**Reason:**

* **Never sold:** `Material` where `Exchange` is null (or `status = AVAILABLE`).

* **Active duration:** `now() - Material.createdAt`.

* **Commonalities:** We have `price`, `category`, `imageUrls` (array length for photo count), and `User.rating` for the seller.
  **Action:** Safe to implement. Excellent query for a correlation matrix.

### ✅ 11. What is the average time (in days) it takes for a newly listed academic item to be marked as sold?

**Status:** Fully Possible
**Reason:** We have the exact timestamps needed. We can measure the time difference between `Material.createdAt` and `Exchange.completedAt` for items that have a linked exchange record.
**Action:** Safe to implement using standard SQL date difference functions.

### ❌ 12. Which specific campus locations (visualized as a heat map) are most frequently used for item exchanges, and how does this density shift during different hours of the day?

**Status:** Not Possible
**Reason:** There is currently no location or coordinates data (latitude/longitude or even text-based meeting spots) being captured on the `Exchange`, `ChatRoom`, or `Material` models.
**Action:** You will need to update the schema to include a location field on the `Exchange` model (or track it as part of the transaction process) before this can be implemented.

### ⚠️ 13. What are the most frequently used words and phrases (word cloud) in the in-app chat messages immediately before a transaction is cancelled or abandoned?

**Status:** Partially Possible
**Reason:** We have the text data in `Message.content`. We can infer "abandonment" by finding `ChatRoom` records that have no corresponding `Exchange` for the same `materialId`. However, extracting "frequently used words" (word clouds) is not a database-level query.
**Action:** The backend team can extract the relevant messages from the database, but they will need to use a Python NLP library (like NLTK or spaCy) within the Django app to process the text, remove stop words, and generate frequencies. 

### ❌ 14. What is the emotional sentiment (positive, neutral, negative) and the most common keywords found in the written reviews left for buyers and sellers?

**Status:** Not Possible
**Reason:** The schema only stores a single numerical `rating` on the `User` model (`Float @default(0)`). There is no table or field storing written text reviews for users or exchanges.
**Action:** You need to create a new `Review` model in Prisma to capture text feedback between users. Even then, determining "emotional sentiment" will require an external NLP service or library.