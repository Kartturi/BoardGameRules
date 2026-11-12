# Task 3: NoSQL Database & Repositories

## Objective
Implement the NoSQL persistence layer to store users, indexed game manuals, pending PDF files, and saved user history.

## Requirements
- Implement NoSQL repository classes for the 4 core collections:
  1. User login information (`UserProfile`)
  2. Ragged game manuals already in the system (`GameManual`)
  3. Pending PDF manuals waiting for the batch job (`PendingPdfManual`)
  4. User history of saved rules, recaps, and Q&A answers (`SavedUserEntry`)
- Provide an in-memory / mock repository implementation alongside the database adapter for fast isolated unit testing.
- Add unit tests verifying CRUD operations and status transitions for all 4 collections.
