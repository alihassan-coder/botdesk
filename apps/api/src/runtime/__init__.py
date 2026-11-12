"""The agent runtime: how a bot run actually happens (graph, model, events, memory).

Runs start inside the API process for now (ADR 0007). Everything here talks to the rest of
the app only through the database and the event bus, so moving it to a job queue later
changes who *starts* a run, not what a run does.
"""
