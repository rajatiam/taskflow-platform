import json, unittest
from backend import exports, repository, service
from unittest.mock import patch
import test_platform as fixtures
import app


class EnhancementTests(unittest.TestCase):
    setUp = fixtures.PlatformTests.setUp
    tearDown = fixtures.PlatformTests.tearDown

    def archive(self):
        row = app.create(self.example)
        response = self.client.delete(
            "/api/records/" + str(row["id"]), headers={"If-Match": str(row["version"])}
        )
        self.assertEqual(response.status_code, 200)
        return self.client.get("/api/admin/archives").json()["items"][0]

    def test_restore_preserves_identity_and_audits(self):
        archived = self.archive()
        response = self.client.post(
            f"/api/admin/archives/{archived['id']}/restore",
            headers={"If-Match": str(archived["version"])},
        )
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()
        self.assertEqual(row["id"], archived["id"])
        self.assertEqual(row["version"], archived["version"] + 1)
        for field in self.example:
            self.assertEqual(row[field], archived[field])
        self.assertEqual(self.client.get("/api/admin/archives").json()["total"], 0)
        self.assertIn(
            "record.restored",
            [
                event["operation"]
                for event in self.client.get("/api/audit").json()["items"]
            ],
        )

    def test_stale_restore_rejected(self):
        archived = self.archive()
        response = self.client.post(
            f"/api/admin/archives/{archived['id']}/restore", headers={"If-Match": "999"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/admin/archives").json()["total"], 1)

    def test_missing_restore_precondition(self):
        archived = self.archive()
        self.assertEqual(
            self.client.post(
                f"/api/admin/archives/{archived['id']}/restore"
            ).status_code,
            428,
        )

    def test_editor_cannot_restore(self):
        archived = self.archive()
        with app.connect() as connection:
            connection.execute(
                "UPDATE users SET role='editor' WHERE id=?", (self.user["id"],)
            )
        self.assertEqual(self.client.get("/api/admin/archives").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/admin/archives/{archived['id']}/restore",
                headers={"If-Match": str(archived["version"])},
            ).status_code,
            403,
        )

    def test_filtered_export_excludes_archives(self):
        self.archive()
        row = app.create(self.example)
        response = self.client.get("/api/exports/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [row["id"]])
        self.assertEqual(
            self.client.get(
                "/api/exports/records", params={"q": "impossible-search-term"}
            ).json(),
            [],
        )
        self.assertIn(
            "text/csv",
            self.client.get("/api/exports/records", params={"format": "csv"}).headers[
                "content-type"
            ],
        )
        self.assertEqual(
            self.client.get(
                "/api/exports/records", params={"format": "bad"}
            ).status_code,
            422,
        )

    def test_export_requires_session(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/exports/records").status_code, 401)

    def test_csv_formula_neutralization(self):
        for value in ["=SUM(1,2)", " @lookup", "+cmd", "-danger", "\tformula"]:
            self.assertTrue(exports.cell(value).startswith("'"))
        self.assertEqual(exports.cell("plain"), "plain")
        self.assertEqual(
            json.loads(exports.render([{"value": "=unsafe"}], "json"))[0]["value"],
            "=unsafe",
        )

    def test_failed_restore_audit_rolls_back_recovery(self):
        archived = self.archive()
        with patch(
            "backend.repository.audit",
            side_effect=RuntimeError("Audit storage unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                service.RecordService(app.DB, app.CONFIG).restore(
                    archived["id"], self.user, str(archived["version"]), "test"
                )
        self.assertEqual(self.client.get("/api/admin/archives").json()["total"], 1)
        self.assertEqual(app.records(), [])
