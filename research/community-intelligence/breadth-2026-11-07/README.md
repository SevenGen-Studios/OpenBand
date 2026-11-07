# Follow pilot coverage review

The November 7, 2026 review started from OpenBand main at `79f666b7`. All-four coverage rose from 10 to 11 of 180 Nations. Kahkewistahaw First Nation gained verified event coverage and had an open job extending beyond the seven-day screening window. Across the site, verified active listings rose from 86 to 92.

Siksika Nation, Brokenhead Ojibway Nation and Kahkewistahaw First Nation meet the pilot screen. Eight Nations retain all four categories through November 14 based on known dates in the current inventory. The three pilot candidates also have recent news in at least two calendar weeks and successful news, events and jobs source checks in the last 14 days. The calculation runs with the existing weekly coverage report.

## Source decisions

- The Kahkewistahaw holiday poster lists eight separate member dinners. The on-reserve November 28 cheque pickup is a distribution notice. The source page and archived poster support the dinner dates, times and locations.
- The Kahkewistahaw Lands Department reported the landfill reclamation complete on October 22. That announcement supplies the date for the completion status.
- The Kahkewistahaw Nutritionist Assistant and Early Childhood Educator postings list November 2026 deadlines and name the 2025–26 school year. Both are held for review until the employer confirms the intended terms.
- The Peguis CFS event announcements have verified publication dates. The image host was unavailable to the collector, so the announcements contribute to news coverage while the event dates remain unverified.
- The Maskwacîs Education Schools Commission job pages returned HTTP 403 to the collector. Those leads remain in source diagnostics.
- The Onion Lake job scan closed six previously unverified postings whose official pages still display application forms after the listed deadlines.
- The Siksika Health Services postings had explicit open-until-filled wording in the linked job PDFs and appeared on the employer's current board on November 7. They retain the normal freshness limit for reviewed listings.

The preservation check now uses the fingerprint of the financial data already in upstream main. The local financial dataset was verified byte-for-byte against that revision.

Reproduce the coverage comparison with the archived inputs in `before/`.

```sh
python -m tools.community_coverage --today 2026-11-07 --baseline research/community-intelligence/breadth-2026-11-07/before
```

## Local Follow pilot

Build the inbox from the four public datasets and serve the generated pages.

```sh
python -m tools.build_follow_updates
python -m tools.build_site
python -m http.server 8768 --bind 127.0.0.1
```

On a pilot profile, choose **Follow**, then open the navigation bell. Choose **Enable device alerts** and grant browser permission to receive a system notification for new items while OpenBand is open. **Send test alert** verifies the device path. Follows and notification choices are stored in this browser.

The publishing jobs refresh the inbox alongside new data. Routine verification passes keep the original discovery time, and the notification worker records delivered items so multiple open tabs can check the same feed. Verified schedule, deadline and project status changes appear as unread in the inbox. Newly discovered items are eligible for device alerts.

The pilot UI is enabled on localhost. Delivery when the site is closed requires a Web Push sender and browser subscription service.
