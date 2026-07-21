from typing import Any


def submit_and_complete(client, path: str, *, json=None, headers=None) -> dict[str, Any]:
    accepted = client.post(path, json=json, headers=headers)
    assert accepted.status_code == 202, accepted.text
    return complete_accepted_task(client, accepted)


def complete_accepted_task(client, accepted) -> dict[str, Any]:
    payload = execute_accepted_task(client, accepted)
    assert payload["status"] in {"completed", "needs_review"}, payload
    assert payload["result"] is not None
    return payload["result"]


def execute_accepted_task(client, accepted) -> dict[str, Any]:
    task_id = accepted.json()["task_id"]
    worker = client.app.state.coursepilot_test_task_worker
    assert worker.run_once() is True
    task = client.get(f"/api/coursepilot/tasks/{task_id}")
    assert task.status_code == 200
    payload = task.json()
    assert payload["status"] in {"completed", "needs_review", "failed"}, payload
    return payload
