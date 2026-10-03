# Business Questions Feasibility Report

**Target Database Schema:** Prisma
**Last Updated:** Following the addition of Ratings, Meeting Proposals, Schedule Blocks, Exchange geolocation data, and Smart Match/Exchange Analytics Events.

## Executive Summary
This document analyzes 14 core business questions to determine if they can be answered using our current database structure. 
*   **Fully Possible:** 12 questions
*   **Partially Possible:** 1 question
*   **Impossible:** 1 question

---

## Detailed Breakdown

### 1. In which screens and features of the app do crashes happen most often, and on which OS versions and device models?
*   **Status:** **Impossible**
*   **Reason:** The database does not track app crashes, operating systems, or device models.
*   **Action:** Implement a dedicated crash reporting tool like Sentry, Firebase Crashlytics, or Datadog on the frontend. Do not attempt to log this in the PostgreSQL database.

### 2. How many listings does a buyer open before contacting a seller, and how many before completing an exchange?
*   **Status:** **Fully Possible**
*   **Reason:** The `AnalyticsEvent` table tracks both `LISTING_VIEW` and `CONTACT_SELLER` events by `userId`.
*   **Action:** Query `AnalyticsEvent` to count `LISTING_VIEW` occurrences prior to a `CONTACT_SELLER` event or a completed `Exchange` (or `EXCHANGE_CONFIRMED` event) for a specific user and material.

### 3. Which photos do sellers upload most (number of photos, angles, close-ups of damage), and how does that relate to the number of buyers who contact them?
*   **Status:** **Partially Possible**
*   **Reason:** We can count the number of photos using the length of the `imageUrls` array in the `Material` model, and correlate that to chat room creations. However, the database cannot evaluate the *content* of the photos (angles, close-ups).
*   **Action:** Query the length of `imageUrls` and group by the count of `ChatRoom` entries. For angles/close-ups, you would need an image analysis AI or manual tagging.

### 4. How many messages do a buyer and a seller exchange in the app chat before they agree on a meeting point, and how long this conversation take?
*   **Status:** **Fully Possible**
*   **Reason:** The `Message` model now includes a `type` field (`TEXT`, `MEETING`) and links to a `MeetingProposal`. We can count messages in a `ChatRoom` up to the timestamp of an accepted `MeetingProposal`.
*   **Action:** Count `Message` rows where `createdAt` is less than the `respondedAt` of a `MeetingProposal` with `status = ACCEPTED`.

### 5. At what time of the day and which days of the week do students publish and browse the most?
*   **Status:** **Fully Possible**
*   **Reason:** `Material.createdAt` tracks publishing times. `AnalyticsEvent.occurredAt` tracks browsing (via `LISTING_VIEW` and `SEARCH`). The new `ScheduleBlock` model also helps cross-reference this with actual user availability.
*   **Action:** Extract the hour and day-of-week from the respective timestamps to build a frequency distribution.

### 6. Which categories of items generate the most listings and the most completed exchanges?
*   **Status:** **Fully Possible**
*   **Reason:** `Material` has a `category` enum (BOOKS, CALCULATORS, etc.), and `Exchange` tracks `status = COMPLETED`.
*   **Action:** Group `Material` and `Exchange` records by `Material.category` and count the totals.

### 7. How many buyers save items in the wishlist, and how many of those saved items end in a purchase after a Smart matching notification?
*   **Status:** **Fully Possible**
*   **Reason:** With the newly added `AnalyticsEventType` values (`SMART_MATCH_SHOWN`, `SMART_MATCH_OPENED`, `SMART_MATCH_RESERVED`, `EXCHANGE_CONFIRMED`), the team no longer needs to rely on complex joins between `WishlistItem`, `Notification`, and `Exchange`.
*   **Action:** Build a direct analytics funnel query on the `AnalyticsEvent` table. Filter by `userId` and `materialId` to track the exact sequence: `WISHLIST_ADD` -> `SMART_MATCH_SHOWN`/`SMART_MATCH_OPENED` -> `SMART_MATCH_RESERVED` or `EXCHANGE_CONFIRMED`.

### 8. Which fields of the listing form do sellers leave empty most often (course, edition, condition, faculty)?
*   **Status:** **Fully Possible**
*   **Reason:** `courseCode`, `edition`, and `condition` are optional on `Material`. `faculty` is optional on `User`.
*   **Action:** Query the total number of `Material` records where these specific fields evaluate to `null`.

### 9. How do prices of the same item vary (same book edition, same model) between sellers, faculties, and item condition?
*   **Status:** **Fully Possible**
*   **Reason:** Both `edition` and `model` are explicitly tracked in the `Material` model, along with `price` and `condition`. The seller's `faculty` is joined via the `User` table.
*   **Action:** Group records by `model` or `edition`, then segment the `price` data by `condition` and `User.faculty`.

### 10. Which listings are published but never sold, how long do they stay active, and what do they have in common?
*   **Status:** **Fully Possible**
*   **Reason:** We can query `Material` where `status = AVAILABLE` and filter by the time elapsed since `createdAt`.
*   **Action:** Filter available materials over a certain age and run aggregate analyses on their `price`, `category`, and `seller` ratings.

### 11. What is the average time (in days) it takes for a newly listed academic item to be marked as sold?
*   **Status:** **Fully Possible**
*   **Reason:** Both `Material.createdAt` and `Exchange.completedAt` exist.
*   **Action:** Calculate the time difference between `Material.createdAt` and `Exchange.completedAt` for all completed exchanges, then compute the average.

### 12. Which specific campus locations (visualized as a heat map) are most frequently used for item exchanges, and how does this density shift during different hours of the day?
*   **Status:** **Fully Possible**
*   **Reason:** The `Exchange` and `MeetingPoint` models now store `lat` and `lng` coordinates, as well as `meetingStartsAt` timestamps.
*   **Action:** Extract spatial data (`lat`, `lng`) and temporal data (`meetingStartsAt`) from `Exchange` and `MeetingPoint` to feed into a heat map visualization tool.

### 13. What are the most frequently used words and phrases (word cloud) in the in-app chat messages immediately before a transaction is cancelled or abandoned?
*   **Status:** **Fully Possible**
*   **Reason:** `Message.content` holds the text, and we can filter by `chatRoomId` linked to an `Exchange` where `status = CANCELLED`.
*   **Action:** Extract all `Message.content` for cancelled exchanges and process the text through a standard NLP library (like NLTK or spaCy) to generate word frequencies.

### 14. What is the emotional sentiment (positive, neutral, negative) and the most common keywords found in the written reviews left for buyers and sellers?
*   **Status:** **Fully Possible**
*   **Reason:** The `Rating` model now includes a `review` text field and an array of `tags`. 
*   **Action:** Retrieve all `review` text and `tags` from the `Rating` model. While the sentiment analysis itself requires external text-processing logic, all the required data is structurally available.
