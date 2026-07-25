import csv
import copy
import io
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from server import (
    DataStore,
    create_oauth_authorization,
    detect_assetto_corsa_installation,
    extract_series_logo,
    extract_track_id,
    generic_series_svg,
    generic_track_map_svg,
    generic_track_svg,
    normalize_assetto_corsa_export,
    normalize_iracing_export,
    normalize_raceroom_result,
    raceroom_profile_slug,
    official_track_slug,
    read_ibt_metadata,
    resolve_assetto_track_asset,
)


def write_fake_ibt(
    path: Path, subsession_id: str, session_type: str = "Race"
) -> None:
    session_info = (
        "WeekendInfo:\n"
        f"  SubSessionID: {subsession_id}\n"
        "  SessionID: 123456\n"
        "  TrackDisplayName: Watkins Glen International\n"
        "DriverInfo:\n"
        "  DriverCarIdx: 0\n"
        "  Drivers:\n"
        "  - CarScreenName: Porsche 911 Cup\n"
        "SessionInfo:\n"
        "  Sessions:\n"
        f"  - SessionType: {session_type}\n"
    ).encode("utf-8")
    var_header_offset = 104
    session_info_offset = var_header_offset + 144
    content = bytearray(session_info_offset + len(session_info))
    struct.pack_into(
        "<10i",
        content,
        0,
        2,
        1,
        60,
        1,
        len(session_info),
        session_info_offset,
        1,
        var_header_offset,
        1,
        4,
    )
    struct.pack_into("<qddii", content, 72, 0, 0.0, 60.0, 10, 3600)
    struct.pack_into("<4i", content, var_header_offset, 4, 0, 1, 0)
    content[var_header_offset + 16 : var_header_offset + 21] = b"Speed"
    content[session_info_offset:] = session_info
    path.write_bytes(content)


class FakeProtector:
    def protect(self, value):
        return f"protected:{value}".encode("utf-8")

    def unprotect(self, value):
        return bytes(value).decode("utf-8").removeprefix("protected:")


class DataStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.store = DataStore(self.root / "test.db", protector=FakeProtector())
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE settings SET value = '100001' WHERE key = 'owner_iracing_id'"
            )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_track_images_use_official_slugs_and_safe_generic_svg(self):
        self.assertEqual(
            official_track_slug("[Retired] Brands Hatch Circuit"),
            "brands-hatch",
        )
        svg = generic_track_svg("Circuito <Prueba> & Test").decode("utf-8")
        self.assertIn("Circuito &lt;Prueba&gt; &amp; Test", svg)
        self.assertNotIn("<Prueba>", svg)

    def test_assetto_track_preview_and_outline_use_local_installation(self):
        install = self.root / "assettocorsa"
        ui = install / "content" / "tracks" / "my_test_track" / "ui"
        layout_ui = ui / "gp"
        layout_ui.mkdir(parents=True)
        (ui / "preview.png").write_bytes(b"preview")
        (layout_ui / "outline.png").write_bytes(b"outline")

        self.assertEqual(detect_assetto_corsa_installation(str(install)), install)
        preview = resolve_assetto_track_asset(
            "My Test Track", "GP", install, "preview"
        )
        outline = resolve_assetto_track_asset(
            "My Test Track", "GP", install, "outline"
        )
        self.assertEqual(preview, (b"preview", "image/png", "assetto-local"))
        self.assertEqual(outline, (b"outline", "image/png", "assetto-local"))

    def test_assetto_track_uses_the_directory_matching_the_requested_layout(self):
        install = self.root / "assettocorsa"
        old_ui = install / "content" / "tracks" / "daytona_2017" / "ui" / "roadcourse"
        lfm_ui = install / "content" / "tracks" / "rt_daytona" / "ui" / "sportscar_m4x"
        old_ui.mkdir(parents=True)
        lfm_ui.mkdir(parents=True)
        (old_ui / "outline.png").write_bytes(b"wrong-daytona")
        (lfm_ui / "outline.png").write_bytes(b"correct-lfm-daytona")

        outline = resolve_assetto_track_asset(
            "Daytona", "SportsCar M4X", install, "outline"
        )

        self.assertEqual(
            outline,
            (b"correct-lfm-daytona", "image/png", "assetto-local"),
        )

    def test_assetto_track_skips_empty_cropped_outline_and_uses_map(self):
        install = self.root / "assettocorsa"
        track = install / "content" / "tracks" / "test_mod"
        layout_ui = track / "ui" / "gp"
        layout_data = track / "gp"
        layout_ui.mkdir(parents=True)
        layout_data.mkdir(parents=True)
        (layout_ui / "outline_cropped.png").write_bytes(b"\0" * 384)
        (layout_data / "map.png").write_bytes(b"usable-map")

        outline = resolve_assetto_track_asset(
            "Test Mod", "GP", install, "outline"
        )

        self.assertEqual(outline, (b"usable-map", "image/png", "assetto-local"))

    def test_series_logo_is_read_from_the_original_iracing_result(self):
        raw_json = json.dumps({"data": {"subsession_id": 1, "series_logo": "seriesid_476.png"}})
        self.assertEqual(extract_series_logo(raw_json), "seriesid_476.png")
        self.assertEqual(
            extract_series_logo(json.dumps({"data": {"series_logo": "../logo.png"}})),
            "",
        )

    def test_generic_series_logo_uses_the_active_simulator(self):
        assetto_logo = generic_series_svg(
            "WorldSimSeries.com | CUPRA LEON SERIES", "assetto-corsa"
        ).decode("utf-8")
        iracing_logo = generic_series_svg(
            "Porsche Cup", "iracing"
        ).decode("utf-8")

        self.assertIn("ASSETTO CORSA", assetto_logo)
        self.assertNotIn("iRACING SERIES", assetto_logo)
        self.assertIn("iRACING SERIES", iracing_logo)

    def test_track_id_and_generic_map_are_safe(self):
        raw_json = json.dumps({"data": {"subsession_id": 1, "track": {"track_id": 434}}})
        self.assertEqual(extract_track_id(raw_json), 434)
        svg = generic_track_map_svg("Circuito <Prueba>").decode("utf-8")
        self.assertIn("Circuito &lt;Prueba&gt;", svg)
        self.assertNotIn("<Prueba>", svg)

    def test_initial_state_contains_demo_league(self):
        state = self.store.get_state()

        self.assertEqual(state["league"]["season"], "2026 Season 3")
        self.assertEqual(state["league"]["weeksCompleted"], 6)
        self.assertEqual(len(state["drivers"]), 8)
        self.assertEqual(len(state["rounds"]), 6)
        self.assertEqual(state["storage"]["raceCount"], 18)

    def test_driver_is_persisted_and_duplicate_is_rejected(self):
        result = self.store.add_driver("999001")
        state = self.store.get_state()

        self.assertTrue(result["pendingValidation"])
        self.assertEqual(len(state["drivers"]), 9)
        self.assertEqual(state["drivers"][-1]["id"], "999001")

        with self.assertRaisesRegex(ValueError, "ya pertenece"):
            self.store.add_driver("999001")

    def test_invalid_driver_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "entre 3 y 12"):
            self.store.add_driver("ABC")

    def test_settings_are_updated(self):
        saved = self.store.update_settings(
            {
                "rankingMode": "races",
                "minimumParticipation": 60,
                "tiebreaker": "wins",
            }
        )
        state = self.store.get_state()

        self.assertEqual(saved["minimumParticipation"], 60)
        self.assertEqual(state["settings"]["rankingMode"], "races")
        self.assertEqual(state["settings"]["tiebreaker"], "wins")

    def test_archive_is_idempotent_for_same_season(self):
        first = self.store.archive_current_season()
        second = self.store.archive_current_season()
        state = self.store.get_state()

        self.assertEqual(first["season"], second["season"])
        self.assertEqual(state["storage"]["archiveCount"], 1)

    def test_backup_creates_valid_database_copy(self):
        result = self.store.create_backup(self.root / "backups")
        backup_path = self.root / "backups" / result["filename"]

        self.assertTrue(backup_path.exists())
        backup_store = DataStore(backup_path)
        self.assertEqual(len(backup_store.get_state()["drivers"]), 8)
        self.assertIsNotNone(self.store.get_state()["storage"]["lastBackup"])

    def test_csv_export_contains_official_and_provisional_drivers(self):
        content = self.store.standings_csv().decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content), delimiter=";"))

        self.assertEqual(rows[0][0], "Posición")
        self.assertEqual(len(rows), 9)
        self.assertIn("Oficial", {row[-1] for row in rows[1:]})
        self.assertIn("Provisional", {row[-1] for row in rows[1:]})

    def test_oauth_authorization_uses_pkce_and_one_time_state(self):
        self.store.save_oauth_client_id("public-client-123")
        authorization = create_oauth_authorization(
            self.store, "http://127.0.0.1:4173/oauth/callback"
        )
        query = parse_qs(urlparse(authorization["authorizationUrl"]).query)

        self.assertEqual(query["client_id"], ["public-client-123"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], ["iracing.auth iracing.profile"])
        session = self.store.consume_oauth_session(query["state"][0])
        self.assertGreaterEqual(len(session["codeVerifier"]), 43)
        with self.assertRaisesRegex(ValueError, "no existe"):
            self.store.consume_oauth_session(query["state"][0])

    def test_oauth_tokens_are_protected_and_can_be_disconnected(self):
        self.store.save_oauth_client_id("public-client-123")
        self.store.save_oauth_tokens(
            {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_in": 600,
                "refresh_token_expires_in": 604800,
                "scope": "iracing.auth iracing.profile",
            },
            {"iracing_name": "Test Driver", "iracing_cust_id": 12345},
        )

        status = self.store.get_oauth_status()
        tokens = self.store.get_oauth_tokens()
        with self.store.connect() as connection:
            stored = connection.execute(
                "SELECT access_token FROM oauth_tokens WHERE id = 1"
            ).fetchone()[0]

        self.assertTrue(status["connected"])
        self.assertEqual(status["profileName"], "Test Driver")
        self.assertEqual(tokens["accessToken"], "access-secret")
        self.assertNotEqual(bytes(stored), b"access-secret")

        self.store.disconnect_oauth()
        self.assertFalse(self.store.get_oauth_status()["connected"])

    def test_iracing_json_is_normalized(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))

        result = normalize_iracing_export(payload)

        self.assertEqual(result["externalEventId"], "98765432")
        self.assertEqual(result["seriesName"], "iRacing Porsche Cup by CONSPIT")
        self.assertEqual(result["raceWeek"], 6)
        self.assertEqual(result["strengthOfField"], 2612)
        self.assertEqual(result["results"][0]["customerId"], "100001")
        self.assertEqual(result["results"][0]["finishPosition"], 1)
        self.assertEqual(result["results"][0]["startPosition"], 3)

    def test_search_results_index_explains_that_full_event_results_are_required(self):
        payload = [
            [
                {
                    "subsession_id": 85950601,
                    "event_type": 2,
                    "event_type_name": "Practice",
                },
                {
                    "subsession_id": 85954304,
                    "event_type": 5,
                    "event_type_name": "Race",
                },
            ]
        ]

        with self.assertRaisesRegex(
            ValueError, "2 sesiones, 1 carreras.*eventresult"
        ):
            normalize_iracing_export(payload)

    def test_practice_result_is_not_imported_as_a_race(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["event_type"] = 2
        payload["event_type_name"] = "Practice"

        with self.assertRaisesRegex(ValueError, "Practice, no una carrera"):
            normalize_iracing_export(payload)

    def test_iracing_import_replaces_demo_and_recalculates(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))

        imported = self.store.import_iracing_result(
            fixture.name, payload, include_all_drivers=True, replace_demo=True
        )
        state = self.store.get_state()
        repeated = self.store.import_iracing_result(
            fixture.name, payload, include_all_drivers=True, replace_demo=True
        )

        self.assertFalse(imported["duplicate"])
        self.assertEqual(imported["linkedDrivers"], 3)
        self.assertFalse(state["demoMode"])
        self.assertEqual(state["storage"]["importCount"], 1)
        self.assertEqual(state["storage"]["raceCount"], 1)
        self.assertEqual(len(state["drivers"]), 3)
        self.assertEqual(state["drivers"][0]["weekly"], 1)
        self.assertEqual(state["drivers"][0]["incidents"], 1)
        self.assertTrue(repeated["duplicate"])

    def test_race_detail_and_head_to_head_analysis(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        self.store.import_iracing_result(fixture.name, payload)

        races = self.store.get_races()
        detail = self.store.get_race_detail(races["races"][0]["id"])
        comparisons = self.store.get_rival_comparisons()

        self.assertEqual(races["ownerIracingId"], "100001")
        self.assertEqual(len(races["races"]), 1)
        self.assertEqual(races["races"][0]["ownerResult"]["finishPosition"], 1)
        self.assertEqual(len(detail["results"]), 3)
        self.assertEqual(detail["summary"]["ownerResult"]["iracingId"], "100001")
        owner_result = detail["summary"]["ownerResult"]
        self.assertGreaterEqual(owner_result["gridScore"], 0)
        self.assertLessEqual(owner_result["gridScore"], 100)
        self.assertGreaterEqual(owner_result["cleanlinessScore"], 0)
        self.assertLessEqual(owner_result["cleanlinessScore"], 100)
        self.assertIn("sof", owner_result["scoreComponents"])
        self.assertIsNotNone(owner_result["newIRating"])
        self.assertIsNotNone(owner_result["newSafetyRating"])
        profile = self.store.get_driver_detail("100001")
        self.assertIsNotNone(profile["summary"]["gridRating"])
        self.assertIsNotNone(profile["summary"]["iratingEnd"])
        self.assertIsNotNone(profile["summary"]["safetyRatingEnd"])
        self.assertEqual(comparisons["summary"]["races"], 1)
        self.assertEqual(comparisons["summary"]["uniqueRivals"], 2)
        self.assertEqual(comparisons["summary"]["recurrentRivals"], 0)
        self.assertTrue(
            all(rival["ownerAhead"] == 1 for rival in comparisons["rivals"])
        )
        self.assertTrue(
            all(len(rival["meetingDetails"]) == 1 for rival in comparisons["rivals"])
        )

    def test_session_detail_aggregates_repeated_drivers_and_ratings(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        first = json.loads(fixture.read_text(encoding="utf-8"))
        second = copy.deepcopy(first)
        second["subsession_id"] = 98765433
        second_results = second["session_results"][1]["results"]
        second_results[0]["finish_position"] = 1
        second_results[0]["finish_position_in_class"] = 1
        second_results[0]["oldi_rating"] = 2482
        second_results[0]["newi_rating"] = 2515
        second_results[0]["old_sub_level"] = 271
        second_results[0]["new_sub_level"] = 278
        second_results[1]["finish_position"] = 0
        second_results[1]["finish_position_in_class"] = 0

        self.store.import_iracing_result("first.json", first)
        self.store.import_iracing_result("second.json", second)
        state = self.store.get_state()
        detail = self.store.get_session_detail(6)
        comparisons = self.store.get_rival_comparisons()
        coincidence_leagues = self.store.get_coincidence_leagues()
        rival_card = next(
            driver for driver in state["drivers"] if driver["id"] == "700002"
        )
        owner = next(
            driver
            for driver in detail["drivers"]
            if driver["iracingId"] == "100001"
        )
        rival = next(
            driver
            for driver in detail["drivers"]
            if driver["iracingId"] == "700002"
        )

        self.assertEqual(detail["session"]["raceCount"], 2)
        self.assertEqual(detail["session"]["uniqueDrivers"], 3)
        self.assertEqual(detail["session"]["repeatedDrivers"], 3)
        self.assertEqual(owner["appearances"], 2)
        self.assertEqual(owner["iratingStart"], 2410)
        self.assertEqual(owner["iratingEnd"], 2515)
        self.assertEqual(owner["iratingChange"], 105)
        self.assertAlmostEqual(owner["safetyRatingStart"], 2.63)
        self.assertAlmostEqual(owner["safetyRatingEnd"], 2.78)
        self.assertEqual(rival_card["meetingsWithOwner"], 2)
        self.assertEqual(rival["meetingsWithOwner"], 2)
        self.assertEqual(rival["ownerAhead"], 1)
        self.assertEqual(rival["rivalAhead"], 1)
        self.assertEqual(len(rival["raceDetails"]), 2)
        self.assertEqual(rival["raceDetails"][0]["ownerPosition"], 1)
        self.assertEqual(rival["raceDetails"][0]["finishPosition"], 2)
        self.assertEqual(rival["raceDetails"][0]["oldIRating"], 2520)
        self.assertEqual(comparisons["summary"]["recurrentRivals"], 2)
        eternal = coincidence_leagues["leagues"]["eternal"]
        self.assertEqual(eternal["summary"]["races"], 2)
        self.assertEqual(eternal["summary"]["recurrentRivals"], 2)
        self.assertEqual(eternal["summary"]["participants"], 3)
        self.assertEqual(eternal["summary"]["duels"], 6)
        self.assertEqual(len(eternal["participants"][0]["raceDetails"]), 2)

    def test_driver_detail_contains_season_stats_tracks_and_races(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        first = json.loads(fixture.read_text(encoding="utf-8"))
        second = copy.deepcopy(first)
        second["subsession_id"] = 98765433
        second["race_week_num"] = 6
        second["track"]["track_name"] = "Road America"
        second_results = second["session_results"][1]["results"]
        second_results[1]["finish_position"] = 0
        second_results[1]["finish_position_in_class"] = 0
        second_results[1]["oldi_rating"] = 2498
        second_results[1]["newi_rating"] = 2528

        self.store.import_iracing_result("first.json", first)
        self.store.import_iracing_result("second.json", second)
        detail = self.store.get_driver_detail("700002")

        self.assertEqual(detail["driver"]["name"], "Segundo Piloto")
        self.assertEqual(detail["summary"]["races"], 2)
        self.assertEqual(detail["summary"]["weeks"], 2)
        self.assertEqual(detail["summary"]["bestFinish"], 1)
        self.assertEqual(detail["summary"]["iratingStart"], 2520)
        self.assertEqual(detail["summary"]["iratingEnd"], 2528)
        self.assertEqual(detail["summary"]["meetingsWithOwner"], 2)
        self.assertEqual(len(detail["tracks"]), 2)
        self.assertEqual(len(detail["races"]), 2)
        self.assertEqual(detail["races"][0]["track"], "Road America")
        self.assertEqual(detail["races"][0]["ownerPosition"], 1)
        road_america = next(
            track
            for track in detail["tracks"]
            if track["track"] == "Road America"
        )
        self.assertEqual(road_america["races"], 1)
        self.assertEqual(road_america["bestFinish"], 1)
        self.assertIn("averageStart", road_america)
        self.assertIn("positionsGained", road_america)
        self.assertIn("bestLapTime", road_america)
        self.assertIn("averageGridScore", road_america)
        self.assertEqual(
            road_america["duelWins"]
            + road_america["duelLosses"]
            + road_america["duelTies"],
            2,
        )
        self.assertEqual(road_america["uniqueRivals"], 2)

    def test_global_driver_detail_combines_series_without_mixing_platforms(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        porsche = json.loads(fixture.read_text(encoding="utf-8"))
        mazda = copy.deepcopy(porsche)
        mazda["subsession_id"] = 98765501
        mazda["series_id"] = 999
        mazda["season_id"] = 7001
        mazda["series_name"] = "Global Mazda MX-5 Fanatec Cup"
        mazda["season_name"] = "Global Mazda MX-5 Fanatec Cup - 2025 Season 4"
        mazda["start_time"] = "2025-11-21T19:45:00Z"
        mazda["track"]["track_name"] = "Okayama International Circuit"

        self.store.import_iracing_result("porsche.json", porsche)
        self.store.import_iracing_result("mazda.json", mazda)

        active = self.store.get_driver_detail("700002")
        global_detail = self.store.get_driver_detail("700002", "global")

        self.assertEqual(active["scope"], "active")
        self.assertEqual(active["summary"]["races"], 1)
        self.assertEqual(global_detail["scope"], "global")
        self.assertEqual(global_detail["summary"]["races"], 2)
        self.assertEqual(global_detail["summary"]["series"], 2)
        self.assertEqual(global_detail["summary"]["seasons"], 2)
        self.assertEqual(len(global_detail["periods"]), 2)
        self.assertEqual(
            {race["seriesName"] for race in global_detail["races"]},
            {
                "iRacing Porsche Cup by CONSPIT",
                "Global Mazda MX-5 Fanatec Cup",
            },
        )
        self.assertTrue(
            all(race["season"] for race in global_detail["races"])
        )

    def test_coincidence_leagues_expose_year_season_and_month_history(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        template = json.loads(fixture.read_text(encoding="utf-8"))
        payloads = []
        for index, (season, start_time) in enumerate(
            [
                ("2026 Season 3", "2026-07-22T19:45:00Z"),
                ("2026 Season 3", "2026-07-23T19:45:00Z"),
                ("2026 Season 3", "2026-08-10T19:45:00Z"),
                ("2025 Season 4", "2025-11-20T19:45:00Z"),
                ("2025 Season 4", "2025-11-21T19:45:00Z"),
            ]
        ):
            payload = copy.deepcopy(template)
            payload["subsession_id"] = 98765440 + index
            payload["season_name"] = season
            payload["start_time"] = start_time
            if start_time.startswith("2026-08"):
                for rival_index, result in enumerate(
                    payload["session_results"][1]["results"][1:], start=1
                ):
                    result["cust_id"] = 880000 + rival_index
                    result["display_name"] = f"Piloto aislado {rival_index}"
            payloads.append(payload)
        for index, payload in enumerate(payloads):
            self.store.import_iracing_result(f"period-{index}.json", payload)

        leagues = self.store.get_coincidence_leagues()

        self.assertEqual(
            [period["label"] for period in leagues["periods"]["yearly"]],
            ["2026", "2025"],
        )
        self.assertEqual(
            [period["label"] for period in leagues["periods"]["season"]],
            ["2026 · Temporada 3", "2025 · Temporada 4"],
        )
        self.assertEqual(len(leagues["periods"]["monthly"]), 2)
        self.assertNotIn(
            "Agosto 2026",
            [
                period["label"]
                for period in leagues["periods"]["monthly"]
            ],
        )
        self.assertEqual(leagues["periods"]["yearly"][0]["summary"]["races"], 2)
        self.assertEqual(leagues["periods"]["yearly"][0]["summary"]["tracks"], 1)
        self.assertEqual(
            leagues["periods"]["yearly"][0]["summary"]["averageMembers"], 3
        )

    def test_custom_championship_filters_period_series_and_selected_drivers(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        first = json.loads(fixture.read_text(encoding="utf-8"))
        second = copy.deepcopy(first)
        second["subsession_id"] = 99887766
        second["start_time"] = "2026-08-10T19:45:00Z"
        self.store.import_iracing_result("custom-first.json", first)
        self.store.import_iracing_result("custom-second.json", second)

        saved = self.store.save_custom_championship(
            {
                "name": "Copa privada",
                "seriesNames": ["iRacing Porsche Cup by CONSPIT"],
                "startDate": "2026-01-01",
                "endDate": "2026-07-31",
                "participantMode": "selected",
                "driverIds": ["700002"],
                "includeOwner": True,
                "minimumRaces": 1,
                "rankingMode": "weekly",
            }
        )
        analysis = self.store.get_coincidence_leagues()
        custom = analysis["customChampionships"][0]

        self.assertEqual(custom["id"], saved["id"])
        self.assertEqual(custom["league"]["summary"]["races"], 1)
        self.assertEqual(custom["league"]["minimumRaces"], 1)
        self.assertEqual(custom["league"]["rankingMode"], "weekly")
        self.assertEqual(
            {driver["iracingId"] for driver in custom["league"]["participants"]},
            {"100001", "700002"},
        )
        self.assertTrue(analysis["options"]["series"])
        self.assertTrue(analysis["options"]["drivers"])

        deleted = self.store.delete_custom_championship(saved["id"])
        self.assertTrue(deleted["deleted"])
        self.assertFalse(
            self.store.get_coincidence_leagues()["customChampionships"]
        )

    def test_weekly_average_gives_each_week_equal_weight(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        first = json.loads(fixture.read_text(encoding="utf-8"))
        second = copy.deepcopy(first)
        second["subsession_id"] = 98765433
        second["session_results"][1]["results"][0]["finish_position"] = 2
        second["session_results"][1]["results"][0]["finish_position_in_class"] = 2
        second["session_results"][1]["results"][0]["incidents"] = 5
        third = copy.deepcopy(first)
        third["subsession_id"] = 98765434
        third["race_week_num"] = 6
        third["track"]["track_name"] = "Road America"
        third["session_results"][1]["results"][0]["finish_position"] = 9
        third["session_results"][1]["results"][0]["finish_position_in_class"] = 9
        third["session_results"][1]["results"][0]["incidents"] = 0

        self.store.import_iracing_result("first.json", first)
        self.store.import_iracing_result("second.json", second)
        self.store.import_iracing_result("third.json", third)
        state = self.store.get_state()
        owner = next(driver for driver in state["drivers"] if driver["id"] == "100001")

        self.assertAlmostEqual(owner["weekly"], 6.0)
        self.assertAlmostEqual(owner["races"], 14 / 3)
        self.assertAlmostEqual(owner["incidents"], 1.5)
        self.assertEqual(owner["weeks"], 2)
        self.assertEqual(owner["racesCount"], 3)

    def test_results_are_grouped_into_automatic_series_and_can_be_selected(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        porsche = json.loads(fixture.read_text(encoding="utf-8"))
        porsche["series_id"] = 476
        porsche["season_id"] = 6298
        other_series = copy.deepcopy(porsche)
        other_series["subsession_id"] = 98765500
        other_series["series_id"] = 999
        other_series["season_id"] = 7001
        other_series["series_name"] = "Global Mazda MX-5 Fanatec Cup"
        other_series["season_name"] = "Global Mazda MX-5 Fanatec Cup - 2026 Season 3"
        other_series["car_classes"][0]["name"] = "Global Mazda MX-5 Cup"

        first_import = self.store.import_iracing_result("porsche.json", porsche)
        second_import = self.store.import_iracing_result("mazda.json", other_series)
        porsche_active_state = self.store.get_state()
        porsche_league = next(
            league
            for league in porsche_active_state["leagues"]
            if league["seriesName"] == "iRacing Porsche Cup by CONSPIT"
        )
        mazda_league = next(
            league
            for league in porsche_active_state["leagues"]
            if league["seriesName"] == "Global Mazda MX-5 Fanatec Cup"
        )
        self.store.set_active_league(mazda_league["id"])
        mazda_state = self.store.get_state()

        self.assertFalse(first_import["leagueCreated"])
        self.assertTrue(second_import["leagueCreated"])
        self.assertEqual(
            porsche_active_state["league"]["seriesName"],
            "iRacing Porsche Cup by CONSPIT",
        )
        self.assertEqual(len(porsche_active_state["leagues"]), 2)
        self.assertEqual(
            mazda_state["league"]["seriesName"], "Global Mazda MX-5 Fanatec Cup"
        )
        self.assertEqual(mazda_state["storage"]["raceCount"], 1)

    def test_importing_past_season_does_not_replace_current_selection(self):
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        current = json.loads(fixture.read_text(encoding="utf-8"))
        current["series_id"] = 476
        current["season_id"] = 6298
        current["season_year"] = 2026
        current["season_quarter"] = 3
        past = copy.deepcopy(current)
        past["subsession_id"] = 98765000
        past["season_id"] = 6111
        past["season_year"] = 2026
        past["season_quarter"] = 2
        past["season_name"] = "iRacing Porsche Cup by CONSPIT - 2026 Season 2"

        self.store.import_iracing_result("current.json", current)
        self.store.import_iracing_result("past.json", past)
        state = self.store.get_state()
        overview = self.store.get_global_overview()

        self.assertEqual(state["league"]["season"], "2026 Season 3")
        self.assertTrue(state["league"]["isCurrent"])
        self.assertEqual(len(overview["seasons"]), 2)
        self.assertEqual(
            next(item for item in overview["seasons"] if item["isCurrent"])["season"],
            "2026 Season 3",
        )

    def test_configured_folder_imports_new_json_and_ignores_others(self):
        import_folder = self.root / "results"
        import_folder.mkdir()
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        shutil.copy2(fixture, import_folder / "race.json")
        (import_folder / "unrelated.json").write_text(
            '{"kind":"not-a-race"}', encoding="utf-8"
        )

        saved = self.store.save_import_folder(str(import_folder), auto_scan=True)
        first_scan = self.store.scan_import_folder()
        second_scan = self.store.scan_import_folder()
        state = self.store.get_state()

        self.assertTrue(saved["autoScan"])
        self.assertEqual(first_scan["scanned"], 2)
        self.assertEqual(first_scan["imported"], 1)
        self.assertEqual(first_scan["ignored"], 1)
        self.assertEqual(second_scan["duplicates"], 1)
        self.assertEqual(state["storage"]["importCount"], 1)
        self.assertTrue(state["settings"]["autoScanImports"])

    def test_assetto_corsa_content_manager_history_is_imported_separately(self):
        sessions_folder = self.root / "assetto-sessions"
        sessions_folder.mkdir()
        payload = {
            "track": "ks_barcelona-layout_gp_lfm",
            "players": [
                {"name": "#2 | Piloto Principal", "car": "ks_porsche_911_gt3", "skin": "01"},
                {"name": "#1 | Alex Rival", "car": "ks_porsche_911_gt3", "skin": "02"},
            ],
            "sessions": [
                {
                    "name": "Qualify",
                    "type": 2,
                    "laps": [],
                    "bestLaps": [
                        {"car": 1, "time": 101000, "lap": 2},
                        {"car": 0, "time": 102000, "lap": 3},
                    ],
                },
                {
                    "name": "Race",
                    "type": 3,
                    "duration": 20,
                    "laps": [
                        {"lap": 0, "car": 0, "sectors": [33000, 33000, 34000], "time": 100000, "cuts": 1, "tyre": "SM"},
                        {"lap": 0, "car": 1, "sectors": [32000, 33000, 34000], "time": 99000, "cuts": 0, "tyre": "SM"},
                    ],
                    "lapstotal": [10, 10],
                    "bestLaps": [
                        {"car": 0, "time": 100000, "lap": 5},
                        {"car": 1, "time": 99000, "lap": 4},
                    ],
                    "raceResult": [1, 0],
                },
            ],
            "__raceIni": "[REMOTE]\nSERVER_IP=127.0.0.1\nSERVER_NAME=lowfuelmotorsport.com | 12345|1\nNAME=Piloto Principal\n",
        }
        result_file = sessions_folder / "260725-120000.json"
        result_file.write_text(json.dumps(payload), encoding="utf-8")
        alias_payload = json.loads(json.dumps(payload))
        alias_payload["players"][0]["name"] = "Alias Principal"
        alias_payload["__raceIni"] = (
            "[REMOTE]\nSERVER_NAME=lowfuelmotorsport.com | 12345|1\n"
            "NAME=Alias Principal\nTEAM=\n"
        )
        alias_file = sessions_folder / "260724-120000.json"
        alias_file.write_text(json.dumps(alias_payload), encoding="utf-8")
        local_payload = json.loads(json.dumps(payload))
        local_payload["players"] = [
            {"name": "Piloto Principal", "car": "ks_porsche_911_gt3", "skin": "01"},
            {"name": "AI Max", "car": "ks_porsche_911_gt3", "skin": "02"},
            {"name": "AI Clara", "car": "ks_porsche_911_gt3", "skin": "03"},
        ]
        local_payload["sessions"][0]["bestLaps"] = []
        local_payload["sessions"][1]["laps"] = [
            {"lap": 0, "car": 0, "sectors": [33000, 33000, 34000], "time": 100000, "cuts": 1, "tyre": "SM"},
            {"lap": 0, "car": 1, "sectors": [32000, 33000, 34000], "time": 99000, "cuts": 0, "tyre": "SM"},
            {"lap": 0, "car": 2, "sectors": [34000, 34000, 34000], "time": 102000, "cuts": 0, "tyre": "SM"},
        ]
        local_payload["sessions"][1]["lapstotal"] = [10, 10, 10]
        local_payload["sessions"][1]["bestLaps"] = [
            {"car": 0, "time": 100000, "lap": 5},
            {"car": 1, "time": 99000, "lap": 4},
            {"car": 2, "time": 102000, "lap": 3},
        ]
        local_payload["sessions"][1]["raceResult"] = [1, 0, 2]
        local_payload["__raceIni"] = "[RACE]\nAI_LEVEL=95\nNAME=Piloto Principal\n"
        local_file = sessions_folder / "260623-120000.json"
        local_file.write_text(json.dumps(local_payload), encoding="utf-8")

        normalized = normalize_assetto_corsa_export(payload, result_file.name)
        self.assertEqual(normalized[0]["platform"], "assetto-corsa")
        self.assertEqual(normalized[0]["seriesName"], "Low Fuel Motorsport")
        self.assertEqual(normalized[0]["results"][1]["name"], "Piloto Principal")
        self.assertEqual(normalized[0]["results"][1]["incidents"], 1)
        self.assertTrue(all(not result["isAi"] for result in normalized[0]["results"]))
        normalized_local = normalize_assetto_corsa_export(
            local_payload, local_file.name
        )
        self.assertFalse(normalized_local[0]["results"][1]["isAi"])
        self.assertTrue(normalized_local[0]["results"][0]["isAi"])
        self.assertTrue(normalized_local[0]["results"][2]["isAi"])

        self.store.save_simulator_config(
            {
                "simulator": "assetto-corsa",
                "folder": str(sessions_folder),
                "ownerIdentity": "Piloto Principal",
                "ownerAliases": ["Piloto Principal", "Alias Principal"],
                "autoScan": True,
            }
        )
        first_scan = self.store.scan_assetto_corsa_folder()
        second_scan = self.store.scan_assetto_corsa_folder()
        state = self.store.get_state()
        overview = self.store.get_global_overview()

        self.assertEqual(first_scan["imported"], 3)
        self.assertEqual(second_scan["duplicates"], 3)
        self.assertEqual(state["league"]["platform"], "assetto-corsa")
        self.assertEqual(state["league"]["seriesName"], "Low Fuel Motorsport")
        self.assertEqual(state["settings"]["ownerDisplayName"], "Piloto Principal")
        self.assertEqual(
            state["settings"]["ownerAliases"], ["Piloto Principal", "Alias Principal"]
        )
        self.assertEqual(state["storage"]["raceCount"], 2)
        self.assertEqual(len(state["drivers"]), 2)
        owner = next(
            driver
            for driver in state["drivers"]
            if driver["id"] == state["settings"]["ownerDriverId"]
        )
        self.assertEqual(owner["racesCount"], 2)
        self.assertEqual(overview["totals"]["races"], 3)
        races = self.store.get_races()["races"]
        self.assertTrue(all(race["ownerResult"] is not None for race in races))
        alias_race = next(
            race for race in races if "260724-120000" in race["externalEventId"]
        )
        detail = self.store.get_race_detail(alias_race["id"])
        owner_result = next(
            result for result in detail["results"] if result["isOwner"]
        )
        self.assertIsNotNone(owner_result["averageLapTime"])
        self.assertGreaterEqual(owner_result["gridScore"], 0)
        self.assertLessEqual(owner_result["gridScore"], 100)
        self.assertGreaterEqual(owner_result["cleanlinessScore"], 0)
        self.assertLessEqual(owner_result["cleanlinessScore"], 100)
        self.assertIn("finish", owner_result["scoreComponents"])
        profile = self.store.get_driver_detail(
            state["settings"]["ownerDriverId"]
        )
        self.assertEqual(profile["summary"]["races"], 2)
        self.assertIsNotNone(profile["summary"]["gridRating"])
        self.assertEqual(
            profile["summary"]["gridRating"]["ratedRaces"], 2
        )
        self.assertIn(
            profile["summary"]["gridRating"]["confidence"],
            {"Baja", "Media", "Alta"},
        )
        session = self.store.get_session_detail(races[0]["week"])
        self.assertGreaterEqual(session["session"]["raceCount"], 1)
        with self.store.connect() as connection:
            local_league = connection.execute(
                """
                SELECT id FROM leagues
                WHERE platform = 'assetto-corsa'
                  AND series_name = 'Carreras locales de Assetto Corsa'
                """
            ).fetchone()
        self.assertIsNotNone(local_league)
        self.store.set_active_league(local_league["id"])
        local_state = self.store.get_state()
        self.assertEqual(local_state["storage"]["raceCount"], 1)
        self.assertEqual(len(local_state["drivers"]), 1)
        self.assertEqual(
            local_state["drivers"][0]["id"],
            local_state["settings"]["ownerDriverId"],
        )
        races = self.store.get_races()["races"]
        local_race = next(
            race for race in races if "260623-120000" in race["externalEventId"]
        )
        local_detail = self.store.get_race_detail(local_race["id"])
        self.assertEqual(local_detail["event"]["fieldSize"], 3)
        self.assertEqual(local_detail["event"]["aiDriversExcluded"], 2)
        self.assertEqual(len(local_detail["results"]), 1)
        self.assertTrue(local_detail["results"][0]["isOwner"])
        self.assertGreaterEqual(local_detail["results"][0]["gridScore"], 0)
        self.assertLessEqual(local_detail["results"][0]["gridScore"], 100)
        coincidence_leagues = self.store.get_coincidence_leagues()
        self.assertTrue(coincidence_leagues["periods"]["monthly"])
        self.assertTrue(
            all(
                period["summary"]["races"] > 0
                for period in coincidence_leagues["periods"]["monthly"]
            )
        )
        self.assertNotIn(
            "Junio 2026",
            [
                period["label"]
                for period in coincidence_leagues["periods"]["monthly"]
            ],
        )

    def test_assetto_corsa_ignores_participants_without_an_original_name(self):
        payload = {
            "track": "macau",
            "players": [
                {"name": "Piloto Principal", "car": "cupra", "skin": "01"},
                {"name": "Rival Ejemplo", "car": "cupra", "skin": "02"},
                {"name": "", "car": "cupra", "skin": "03"},
                {"car": "cupra", "skin": "04"},
            ],
            "sessions": [
                {
                    "name": "Race",
                    "type": 3,
                    "duration": 10,
                    "laps": [],
                    "lapstotal": [3, 3, 0, 0],
                    "bestLaps": [],
                    "raceResult": [0, 1, 2, 3],
                }
            ],
            "__raceIni": (
                "[REMOTE]\nSERVER_IP=127.0.0.1\n"
                "SERVER_NAME=lowfuelmotorsport.com | 12345|1\n"
            ),
        }

        normalized = normalize_assetto_corsa_export(
            payload, "241028-211300.json"
        )[0]

        self.assertEqual(
            [result["name"] for result in normalized["results"]],
            ["Piloto Principal", "Rival Ejemplo"],
        )
        self.assertEqual(normalized["fieldSize"], 2)

    def test_ibt_metadata_and_telemetry_folder_are_indexed_and_linked(self):
        telemetry_folder = self.root / "telemetry"
        telemetry_folder.mkdir()
        race_ibt = telemetry_folder / "race.ibt"
        practice_ibt = telemetry_folder / "practice.ibt"
        write_fake_ibt(race_ibt, "98765432", "Race")
        write_fake_ibt(practice_ibt, "12345000", "Practice")
        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        self.store.import_iracing_result(fixture.name, payload)

        metadata = read_ibt_metadata(race_ibt)
        saved = self.store.save_telemetry_folder(
            str(telemetry_folder), auto_scan=True
        )
        scan = self.store.scan_telemetry_folder()
        overview = self.store.get_telemetry_overview()
        state = self.store.get_state()

        self.assertEqual(metadata["subsessionId"], "98765432")
        self.assertEqual(metadata["sessionType"], "Race")
        self.assertEqual(metadata["tickRate"], 60)
        self.assertEqual(metadata["sampleCount"], 3600)
        self.assertIn("Speed", metadata["channels"])
        self.assertTrue(saved["autoScan"])
        self.assertEqual(scan["added"], 2)
        self.assertEqual(scan["linked"], 1)
        self.assertEqual(scan["practice"], 1)
        self.assertEqual(len(overview["files"]), 2)
        self.assertEqual(state["storage"]["telemetryCount"], 2)
        self.assertEqual(state["storage"]["linkedTelemetryCount"], 1)
        self.assertEqual(state["storage"]["practiceTelemetryCount"], 1)

    def test_unchanged_unlinked_telemetry_does_not_trigger_repeated_updates(self):
        telemetry_folder = self.root / "telemetry"
        telemetry_folder.mkdir()
        race_ibt = telemetry_folder / "pending-race.ibt"
        write_fake_ibt(race_ibt, "98765499", "Race")
        self.store.save_telemetry_folder(str(telemetry_folder), auto_scan=True)

        first_scan = self.store.scan_telemetry_folder()
        second_scan = self.store.scan_telemetry_folder()

        self.assertEqual(first_scan["added"], 1)
        self.assertEqual(second_scan["updated"], 0)
        self.assertEqual(second_scan["unchanged"], 1)

        fixture = Path(__file__).parent / "fixtures" / "iracing-result.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["subsession_id"] = 98765499
        self.store.import_iracing_result("matching-race.json", payload)
        linked_scan = self.store.scan_telemetry_folder()

        self.assertEqual(linked_scan["updated"], 1)
        self.assertEqual(linked_scan["linked"], 1)

    def test_import_folder_must_exist(self):
        with self.assertRaisesRegex(ValueError, "no existe"):
            self.store.save_import_folder(
                str(self.root / "missing-folder"), auto_scan=False
            )

    def test_raceroom_result_keeps_coincidences_and_marks_short_races(self):
        payload = {
            "RaceHash": "abc123",
            "RaceFinishTime": 1_720_000_000,
            "TrackId": {"Id": 1, "Name": "RaceRoom Raceway"},
            "TrackLayoutId": {"Id": 2, "Name": "Grand Prix"},
            "RaceResult": [
                {
                    "UserId": 10,
                    "FullName": "Piloto referencia",
                    "FinishPosition": 1,
                    "StartPosition": 2,
                    "Laps": [
                        {"Time": 90_000, "Valid": True} for _ in range(10)
                    ],
                    "Incidents": 1,
                    "Starter": True,
                    "RatingBefore": 1500.5,
                    "RatingAfter": 1512.75,
                    "RatingChange": 12.25,
                    "ReputationBefore": 80.0,
                    "ReputationAfter": 81.5,
                    "ReputationChange": 1.5,
                    "CarClass": {"Id": 3, "Name": "Touring Cars"},
                },
                {
                    "UserId": 20,
                    "FullName": "Rival retirada",
                    "FinishPosition": 2,
                    "StartPosition": 1,
                    "Laps": [
                        {"Time": 91_000, "Valid": True} for _ in range(4)
                    ],
                    "Incidents": 3,
                    "Starter": True,
                    "RatingChange": -4.5,
                    "ReputationChange": -1.0,
                    "CarClass": {"Id": 3, "Name": "Touring Cars"},
                },
            ],
        }

        normalized = normalize_raceroom_result(payload, "10", 50)
        result = self.store._import_normalized_result(
            "raceroom-abc123.json", payload, normalized
        )

        self.assertFalse(result["duplicate"])
        self.assertEqual(normalized["platform"], "raceroom")
        self.assertEqual(normalized["results"][1]["raceRoom"]["distancePercent"], 40)
        self.assertFalse(normalized["results"][1]["raceRoom"]["scoringEligible"])
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT scoring_eligible, distance_percent FROM race_results ORDER BY finish_position"
            ).fetchall()
        self.assertEqual([row["scoring_eligible"] for row in rows], [1, 0])
        self.assertEqual(rows[1]["distance_percent"], 40)

    def test_raceroom_profile_accepts_public_and_internal_urls(self):
        self.assertEqual(
            raceroom_profile_slug(
                "https://game.raceroom.com/users/example-driver/career"
            ),
            "example-driver",
        )
        self.assertEqual(
            raceroom_profile_slug(
                "https://game.raceroom.com/r3e/users/example-driver/career"
            ),
            "example-driver",
        )
        self.assertEqual(
            raceroom_profile_slug("example-driver"), "example-driver"
        )


if __name__ == "__main__":
    unittest.main()
