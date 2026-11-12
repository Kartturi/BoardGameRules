# Task 7: AI Fallback & Quick Recap Generator Module

## Objective
Implement the AI module that generates game rules when no manual is found, creates short Quick Recaps, and synthesizes RAG Q&A answers.

## Requirements
- Define Pydantic v2 `BaseModel` schemas (`response_schema`) for structured Gemini outputs and map them into domain dataclasses.
- Generate structured rules for a requested board game using the LLM when both existing RAG and internet fetching fail.
- Generate a concise "Quick Recap" summary of a game's rules on demand.
- Generate grounded answers to user rule questions using retrieved RAG chunks.
- Add unit tests verifying prompt construction, response parsing, and source attribution (RAG-grounded vs AI-generated fallback).
