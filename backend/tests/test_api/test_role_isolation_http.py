"""HTTP regression coverage for named specialist workspace boundaries."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/finance/folios", {"branch_id": 1}),
        ("/api/v1/pms/room-types", {"branch_id": 1}),
        ("/api/v1/beach/inventory", {"branch_id": 1}),
        ("/api/v1/dining/orders", {"branch_id": 1}),
        ("/api/v1/maintenance/assets", {"branch_id": 1}),
        ("/api/v1/inventory/warehouses", {"branch_id": 1}),
        ("/api/v1/leasing/contracts", {"branch_id": 1}),
        ("/api/v1/hub/pages", {"branch_id": 1}),
        ("/api/v1/hr/employees", {"branch_id": 1}),
        ("/api/v1/crm/customers", {"branch_id": 1}),
    ],
)
def test_timeshare_admin_cannot_open_other_resort_workspaces(
    client: TestClient,
    timeshare_admin_headers,
    path: str,
    params: dict[str, int],
):
    response = client.get(path, params=params, headers=timeshare_admin_headers)
    assert response.status_code == 403, (path, response.text)


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/pms/room-types", {"branch_id": 1}),
        ("/api/v1/beach/inventory", {"branch_id": 1}),
        ("/api/v1/dining/orders", {"branch_id": 1}),
        ("/api/v1/leasing/contracts", {"branch_id": 1}),
        ("/api/v1/hr/employees", {"branch_id": 1}),
        ("/api/v1/crm/customers", {"branch_id": 1}),
    ],
)
def test_accountant_is_limited_to_finance_not_operations(
    client: TestClient,
    accountant_headers,
    path: str,
    params: dict[str, int],
):
    response = client.get(path, params=params, headers=accountant_headers)
    assert response.status_code == 403, (path, response.text)
