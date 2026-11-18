"""Marketplace templates: ready-made bots an organization hires (`GET /templates`,
`POST /orgs/{id}/templates/{templateId}/hire`). The catalogue is the same for every organization."""

from src.templates.catalogue import TEMPLATES

__all__ = ["TEMPLATES"]
