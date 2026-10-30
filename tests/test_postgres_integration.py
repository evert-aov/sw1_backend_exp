"""Integración exclusiva con PostgreSQL: esquema efímero propio, nunca SQLite."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import socket
from threading import Barrier, Event
import unittest
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.auth.entity.user import User
from app.auth.dto.auth_dto import RegisterDTO
from app.auth.service.auth_service import AuthService
from unittest.mock import patch
from app.booking.dto.booking_dto import BookingCreateDTO
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.service.booking_service import BookingService
from app.booking.service.stripe_service import StripeService
from app.booking.entity.payment import Payment, PaymentStatusEnum
from app.booking.entity.stripe_event import StripeEvent
from app.booking.entity.ticket import Ticket
from app.matching.dto.matching_dto import MatchingApplicationDTO
from app.matching.entity.matching_member import MatchingMember
from app.matching.entity.search_log import SearchLog
from app.matching.service.matching_service import MatchingAlgorithmService
from app.matching.service.demand_prediction_service import DemandPredictionService
from app.notifications.entity import Notification
from app.notifications.service import NotificationService
from app.experience.dto.experience_dto import ExperienceFilterDTO
from app.experience.service.experience_service import ExperienceService
from unittest.mock import MagicMock
from app.core.config import settings
from app.core.database import Base, load_all_entities
from app.core.security import create_access_token, decode_token, revoke_token
from app.experience.entity.category import Category
from app.experience.entity.experience import (
    Experience,
    ExperienceStatusEnum,
    ModalityEnum,
)


class PostgreSQLIntegrationTests(unittest.TestCase):
    """Ejecuta transacciones reales únicamente cuando el entorno permite llegar al servidor."""

    @classmethod
    def setUpClass(cls):
        """Crea un esquema aislado y verifica search_path antes de cualquier DDL."""
        url = make_url(settings.database_url)
        try:
            if url.host and url.host.startswith("/"):
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.connect(f"{url.host}/.s.PGSQL.{url.port or 5432}")
            else:
                with socket.create_connection(
                    (url.host or "localhost", url.port or 5432), timeout=2
                ):
                    pass
        except PermissionError as error:
            raise unittest.SkipTest(
                "PostgreSQL no accesible: el entorno deniega sockets; integración NO verificada"
            ) from error
        load_all_entities()
        cls.schema = "experiencia_test_" + uuid4().hex
        cls.admin_engine = create_engine(
            settings.database_url, connect_args={"connect_timeout": 3}
        )
        with cls.admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.addClassCleanup(cls.cleanup_schema)
        # La configuración de esta conexión sustituye únicamente search_path del esquema de pruebas.
        test_url = url.difference_update_query(["options"])
        cls.engine = create_engine(
            test_url,
            connect_args={
                "connect_timeout": 3,
                "options": f"-csearch_path={cls.schema} -ctimezone=UTC",
            },
        )
        with cls.engine.connect() as connection:
            if connection.scalar(text("SELECT current_schema()")) != cls.schema:
                raise RuntimeError(
                    "Destino de pruebas incorrecto: no se creará ninguna tabla"
                )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine, expire_on_commit=False)

    @classmethod
    def cleanup_schema(cls):
        """Elimina exclusivamente el esquema generado por esta clase, incluso tras fallos."""
        if hasattr(cls, "engine"):
            cls.engine.dispose()
        with cls.admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.admin_engine.dispose()

    def event(self, price="100.00", capacity=1):
        """Crea actores y un evento de prueba con IDs nuevos sin tocar datos de trabajo."""
        with self.sessions() as session:
            host = User(
                first_name="Host",
                email=uuid4().hex + "@example.com",
                hashed_password="unused",
                is_active=True,
            )
            users = [
                User(
                    first_name="Buyer",
                    email=uuid4().hex + "@example.com",
                    hashed_password="unused",
                    is_active=True,
                )
                for _ in range(2)
            ]
            category = Category(name=uuid4().hex)
            session.add_all([host, category, *users])
            session.flush()
            event = Experience(
                host_id=host.id,
                category_id=category.id,
                title="Integration event",
                description="A PostgreSQL-only test event",
                modality=ModalityEnum.VIRTUAL,
                status=ExperienceStatusEnum.OPEN,
                price=Decimal(price),
                min_capacity=1,
                max_capacity=capacity,
                reserved_slots=0,
                event_date=(datetime.now(timezone.utc) + timedelta(days=1)).replace(
                    tzinfo=None
                ),
            )
            session.add(event)
            session.commit()
            return event.id, host.id, [user.id for user in users]

    def test_host_can_configure_own_place_edit_and_delete_empty_experience(self):
        from app.experience.service.venue_service import VenueService
        from app.experience.dto.experience_dto import (
            VenueCreateDTO,
            ExperienceUpdateDTO,
        )

        event_id, host_id, users = self.event(capacity=2)
        with self.sessions() as session:
            venues = VenueService(session)
            venue = venues.register_venue(
                host_id,
                VenueCreateDTO(
                    name="Own venue",
                    address="Test address",
                    city="Test city",
                    max_capacity=10,
                ),
            )
            self.assertEqual([v.id for v in venues.get_my_venues(host_id)], [venue.id])
            self.assertEqual(venues.get_my_venues(users[0]), [])
            venue = venues.update_my_venue(
                venue.id,
                host_id,
                VenueCreateDTO(
                    name="Updated venue",
                    address="Test address",
                    city="Test city",
                    max_capacity=12,
                ),
            )
            service = ExperienceService(session)
            service.update_experience(
                event_id,
                host_id,
                ExperienceUpdateDTO(
                    title="Updated event",
                    modality=ModalityEnum.IN_PERSON,
                    venue_id=venue.id,
                ),
            )
            own = service.get_my_hosted_experience(event_id, host_id)
            self.assertTrue(own.can_edit)
            self.assertTrue(own.can_delete)
            self.assertEqual(own.venue_id, venue.id)
            service.delete_experience(event_id, host_id)
            self.assertIsNone(session.get(Experience, event_id))

    def test_host_cannot_edit_delete_or_move_venue_after_attendance(self):
        from app.experience.service.venue_service import VenueService
        from app.experience.dto.experience_dto import (
            VenueCreateDTO,
            ExperienceUpdateDTO,
        )

        event_id, host_id, users = self.event(price="0.00", capacity=2)
        with self.sessions() as session:
            venues = VenueService(session)
            venue = venues.register_venue(
                host_id,
                VenueCreateDTO(name="Own venue", city="Test city", max_capacity=10),
            )
            ExperienceService(session).update_experience(
                event_id,
                host_id,
                ExperienceUpdateDTO(modality=ModalityEnum.IN_PERSON, venue_id=venue.id),
            )
            booking = BookingService(session).create_booking(
                users[0], BookingCreateDTO(experience_id=event_id), str(uuid4())
            )
            for action in [
                lambda: ExperienceService(session).update_experience(
                    event_id, host_id, ExperienceUpdateDTO(title="Changed")
                ),
                lambda: ExperienceService(session).delete_experience(event_id, host_id),
                lambda: venues.update_my_venue(
                    venue.id,
                    host_id,
                    VenueCreateDTO(name="Moved", city="Other city", max_capacity=10),
                ),
            ]:
                with self.assertRaises(HTTPException) as failure:
                    action()
                self.assertEqual(failure.exception.status_code, 409)
                session.rollback()
            self.assertEqual(
                session.get(Booking, booking.id).status, BookingStatusEnum.PAID
            )
            self.assertEqual(
                session.query(Ticket).filter(Ticket.booking_id == booking.id).count(), 1
            )

    def test_edit_and_new_booking_serialize_at_experience_lock(self):
        from app.experience.dto.experience_dto import ExperienceUpdateDTO

        event_id, host_id, users = self.event(capacity=2)
        barrier = Barrier(2)

        def edit():
            with self.sessions() as session:
                barrier.wait(timeout=5)
                try:
                    ExperienceService(session).update_experience(
                        event_id, host_id, ExperienceUpdateDTO(price=200)
                    )
                    return "UPDATED"
                except HTTPException as error:
                    session.rollback()
                    if error.status_code != 409:
                        raise
                    return "BLOCKED"

        def book():
            with self.sessions() as session:
                barrier.wait(timeout=5)
                return (
                    BookingService(session)
                    .create_booking(
                        users[0], BookingCreateDTO(experience_id=event_id), str(uuid4())
                    )
                    .total_amount
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            edit_result = pool.submit(edit)
            booking_result = pool.submit(book)
            updated, amount = (
                edit_result.result(timeout=10),
                booking_result.result(timeout=10),
            )
        self.assertIn((updated, amount), [("UPDATED", 200), ("BLOCKED", 100)])

    def test_admin_assigns_multiple_roles_persistently_without_self_demotion(self):
        from app.admin.controller import assign_roles
        from app.auth.repository.role_repository import RoleRepository
        from app.auth.repository.user_repository import UserRepository

        event_id, admin_id, users = self.event()
        with self.sessions() as session:
            role = RoleRepository(session).get_or_create_pending("ADMIN")
            UserRepository(session).assign_role(admin_id, role.id)
            profile = assign_roles(
                session, admin_id, users[0], ["HOST", "ATTENDEE", "HOST"]
            )
            self.assertEqual(set(profile.roles), {"HOST", "ATTENDEE"})
            self.assertEqual(len(UserRepository(session).get_user_roles(users[0])), 2)
            with self.assertRaises(HTTPException) as failure:
                assign_roles(session, admin_id, admin_id, ["HOST"])
            self.assertEqual(failure.exception.status_code, 409)
            self.assertIn("ADMIN", UserRepository(session).get_user_roles(admin_id))

    def test_role_seed_is_repeatable_and_preserves_existing_changes(self):
        from app.core.demo_seed import build_demo_plan, seed_demo_connection
        from app.booking.service.stripe_gateway import StripeGateway
        from sqlalchemy import select, func

        dataset = "demo-" + uuid4().hex[:10]
        plan = build_demo_plan(dataset)
        with patch.object(
            StripeGateway,
            "_client",
            side_effect=AssertionError("No debe contactar Stripe"),
        ) as gateway:
            with self.engine.begin() as connection:
                report = seed_demo_connection(connection, plan)
            self.assertEqual(
                (report["users"], report["venues"], report["experiences"]), (6, 3, 10)
            )
            self.assertEqual(
                (
                    report["bookings"],
                    report["tickets"],
                    report["matching_members"],
                    report["notifications"],
                ),
                (4, 4, 3, 9),
            )
            editable_id = next(
                item["id"] for item in plan["experiences"] if item["key"] == "editable"
            )
            admin_id = plan["users"][0]["id"]
            with self.sessions() as session:
                event = session.get(Experience, editable_id)
                original_date = event.event_date
                event.title = "Título editado desde la web"
                password_hash = session.get(User, admin_id).hashed_password
                session.commit()
            with self.engine.begin() as connection:
                repeated = seed_demo_connection(
                    connection,
                    build_demo_plan(
                        dataset, datetime.now(timezone.utc) + timedelta(days=1)
                    ),
                    "AnotherDemoPassword!",
                )
            self.assertEqual(report, repeated)
            with self.sessions() as session:
                event = session.get(Experience, editable_id)
                self.assertEqual(event.title, "Título editado desde la web")
                self.assertEqual(event.event_date, original_date)
                self.assertEqual(
                    session.get(User, admin_id).hashed_password, password_hash
                )
                event_ids = [item["id"] for item in plan["experiences"]]
                self.assertEqual(
                    session.scalar(
                        select(func.count())
                        .select_from(Payment)
                        .join(Booking)
                        .where(Booking.experience_id.in_(event_ids))
                    ),
                    0,
                )
            gateway.assert_not_called()

    def test_role_seed_does_not_take_over_an_existing_email(self):
        from app.core.demo_seed import (
            build_demo_plan,
            seed_demo_connection,
            DemoSeedConflict,
        )
        from app.auth.repository.user_repository import UserRepository

        plan = build_demo_plan("conflict-" + uuid4().hex[:8])
        with self.sessions() as session:
            original = User(
                first_name="Existing",
                email=plan["users"][0]["email"],
                hashed_password="original-hash",
                is_active=True,
            )
            session.add(original)
            session.commit()
            original_id = original.id
        with self.assertRaises(DemoSeedConflict):
            with self.engine.begin() as connection:
                seed_demo_connection(connection, plan)
        with self.sessions() as session:
            self.assertEqual(UserRepository(session).get_user_roles(original_id), [])
            self.assertEqual(
                session.get(User, original_id).hashed_password, "original-hash"
            )
            for item in plan["users"]:
                self.assertIsNone(session.get(User, item["id"]))

    def test_role_seed_rolls_back_service_commits_when_later_step_fails(self):
        from app.core.demo_seed import build_demo_plan, seed_demo_connection

        plan = build_demo_plan("rollback-" + uuid4().hex[:8])
        with patch(
            "app.core.demo_seed.MatchingAlgorithmService.apply_for_matching",
            side_effect=RuntimeError("controlled failure after bookings"),
        ):
            with self.assertRaises(RuntimeError):
                with self.engine.begin() as connection:
                    seed_demo_connection(connection, plan)
        with self.sessions() as session:
            for item in plan["users"]:
                self.assertIsNone(session.get(User, item["id"]))
            for item in plan["experiences"]:
                self.assertIsNone(session.get(Experience, item["id"]))

    def test_stripe_confirmation_duplicates_and_pending_refund_are_atomic(self):
        """Proveedor controlado, transacciones PG reales y ninguna emisión duplicada."""
        event_id, host_id, users = self.event(capacity=2)
        gateway = MagicMock()
        session_id = "cs_test_" + uuid4().hex
        gateway.create_checkout.return_value = {
            "id": session_id,
            "url": "https://checkout.stripe.com/c/pay/test",
        }
        with self.sessions() as session:
            booking = BookingService(session).create_booking(
                users[0], BookingCreateDTO(experience_id=event_id), str(uuid4())
            )
            service = StripeService(session, gateway)
            service.create_checkout_session(booking.id, users[0])
            remote = {
                "id": session_id,
                "client_reference_id": booking.id,
                "payment_status": "paid",
                "amount_total": 10000,
                "currency": "bob",
                "payment_intent": "pi_" + uuid4().hex,
                "status": "complete",
            }
            event = {
                "id": "evt_" + uuid4().hex,
                "type": "checkout.session.completed",
                "data": {"object": remote},
            }
            gateway.verify_event.return_value = event
            self.assertEqual(
                service.handle_webhook_event(b"signed-by-test-provider", "test")[
                    "outcome"
                ],
                "PAID",
            )
            self.assertEqual(
                service.handle_webhook_event(b"signed-by-test-provider", "test")[
                    "outcome"
                ],
                "DUPLICATE",
            )
            gateway.retrieve_checkout.return_value = remote
            service.reconcile_booking(booking.id, users[0])
            self.assertEqual(
                session.query(Ticket).filter(Ticket.booking_id == booking.id).count(), 1
            )
            self.assertEqual(session.get(Experience, event_id).reserved_slots, 1)
            self.assertEqual(BookingService(session).host_income(host_id)[0].net, 92)
            self.assertEqual(BookingService(session).host_income(users[0]), [])

            gateway.refund.return_value = {
                "id": "re_" + uuid4().hex,
                "status": "pending",
            }
            result = service.request_refund(booking.id, users[0])
            self.assertEqual(result.status, BookingStatusEnum.PAID)
            self.assertEqual(result.refund_status, "pending")
            with self.assertRaises(HTTPException):
                BookingService(session).check_in(result.tickets[0].id, host_id)
            gateway.retrieve_refund.return_value = {
                "id": gateway.refund.return_value["id"],
                "status": "succeeded",
            }
            service.process_refund(booking.id)
            service.process_refund(booking.id)
            self.assertEqual(
                session.get(Booking, booking.id).status, BookingStatusEnum.REFUNDED
            )
            self.assertEqual(session.get(Experience, event_id).reserved_slots, 0)
            self.assertEqual(BookingService(session).host_income(host_id)[0].gross, 0)
            self.assertEqual(
                BookingService(session).host_income(host_id)[0].refunded, 100
            )

    def test_late_stripe_payment_is_refunded_without_tickets(self):
        """Un cobro posterior al vencimiento persiste como devolución y no ocupa cupos."""
        event_id, _, users = self.event()
        gateway = MagicMock()
        gateway.create_checkout.return_value = {
            "id": "cs_" + uuid4().hex,
            "url": "https://checkout.stripe.com/c/pay/test",
        }
        with self.sessions() as session:
            booking = BookingService(session).create_booking(
                users[0], BookingCreateDTO(experience_id=event_id), str(uuid4())
            )
            service = StripeService(session, gateway)
            checkout = service.create_checkout_session(booking.id, users[0])
            stored = session.get(Booking, booking.id)
            stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            session.commit()
            remote = {
                "id": checkout.stripe_session_id,
                "client_reference_id": booking.id,
                "payment_status": "paid",
                "amount_total": 10000,
                "currency": "bob",
                "payment_intent": "pi_" + uuid4().hex,
                "status": "complete",
            }
            gateway.verify_event.return_value = {
                "id": "evt_" + uuid4().hex,
                "type": "checkout.session.completed",
                "data": {"object": remote},
            }
            self.assertEqual(
                service.handle_webhook_event(b"signed", "test")["outcome"],
                "REFUND_PENDING",
            )
            self.assertEqual(
                session.query(Ticket).filter(Ticket.booking_id == booking.id).count(), 0
            )
            gateway.refund.return_value = {
                "id": "re_" + uuid4().hex,
                "status": "succeeded",
            }
            service.process_refund(booking.id)
            self.assertEqual(session.get(Experience, event_id).reserved_slots, 0)
            self.assertEqual(
                session.get(Booking, booking.id).status, BookingStatusEnum.REFUNDED
            )

    def test_checkout_recovers_attempt_after_lost_provider_response(self):
        """Conserva parámetros y clave remota cuando el SDK pierde la respuesta."""
        import stripe

        event_id, _, users = self.event()
        gateway = MagicMock()
        gateway.create_checkout.side_effect = stripe.APIConnectionError("response lost")
        with self.sessions() as session:
            booking = BookingService(session).create_booking(
                users[0], BookingCreateDTO(experience_id=event_id), str(uuid4())
            )
            service = StripeService(session, gateway)
            with self.assertRaises(HTTPException):
                service.create_checkout_session(booking.id, users[0])
            attempt = (
                session.query(Payment).filter(Payment.booking_id == booking.id).one()
            )
            self.assertTrue(attempt.payment_metadata["checkout_params"])
            self.assertEqual(
                attempt.payment_metadata["last_checkout_error"]["category"],
                "APIConnectionError",
            )
            first_call = gateway.create_checkout.call_args
            gateway.create_checkout.side_effect = None
            gateway.create_checkout.return_value = {
                "id": "cs_" + uuid4().hex,
                "url": "https://checkout.stripe.com/c/pay/test",
            }
            service.create_checkout_session(booking.id, users[0])
            self.assertEqual(gateway.create_checkout.call_args, first_call)
            self.assertEqual(
                session.query(Payment).filter(Payment.booking_id == booking.id).count(),
                1,
            )
            self.assertNotIn(
                "last_checkout_error", session.get(Payment, attempt.id).payment_metadata
            )

    def test_rejected_legacy_checkout_migrates_durable_params_without_creating_another_payment(
        self,
    ):
        """Reproduce payment_method_types rechazado y recupera la misma reserva en PostgreSQL."""
        import stripe

        event_id, _, users = self.event()
        gateway = MagicMock()
        with self.sessions() as session:
            booking = BookingService(session).create_booking(
                users[0], BookingCreateDTO(experience_id=event_id), str(uuid4())
            )
            legacy_params = {
                "mode": "payment",
                "payment_method_types": ["card"],
                "client_reference_id": booking.id,
                "line_items": [
                    {
                        "quantity": 1,
                        "price_data": {"currency": "bob", "unit_amount": 10000},
                    }
                ],
            }
            payment = Payment(
                booking_id=booking.id,
                amount=Decimal("100.00"),
                currency="BOB",
                status=PaymentStatusEnum.PENDING,
                payment_metadata={"checkout_params": legacy_params},
            )
            session.add(payment)
            session.commit()

            def create_remote(params, key):
                if "payment_method_types" in params:
                    raise stripe.InvalidRequestError(
                        "payment_method_types is no longer supported",
                        "payment_method_types",
                    )
                with self.sessions() as verifier:
                    saved = verifier.get(Payment, payment.id)
                    self.assertEqual(saved.payment_metadata["checkout_params"], params)
                    self.assertEqual(
                        saved.payment_metadata["checkout_params_version"], 2
                    )
                return {
                    "id": "cs_" + uuid4().hex,
                    "url": "https://checkout.stripe.com/c/pay/upgraded",
                }

            gateway.create_checkout.side_effect = create_remote
            service = StripeService(session, gateway)
            with self.assertRaises(HTTPException) as first_error:
                service.create_checkout_session(booking.id, users[0])
            self.assertEqual(first_error.exception.status_code, 422)
            result = service.create_checkout_session(booking.id, users[0])
            self.assertEqual(result.booking_id, booking.id)
            self.assertEqual(
                gateway.create_checkout.call_args_list[0].args[1],
                gateway.create_checkout.call_args_list[1].args[1],
            )
            self.assertNotIn(
                "payment_method_types",
                session.get(Payment, payment.id).payment_metadata["checkout_params"],
            )
            self.assertEqual(
                session.query(Payment).filter(Payment.booking_id == booking.id).count(),
                1,
            )
            self.assertEqual(
                session.get(Booking, booking.id).status, BookingStatusEnum.PENDING
            )

    def test_matching_get_is_read_only_and_interest_does_not_sell_seats(self):
        event_id, host_id, users = self.event(capacity=4)
        with self.sessions() as session:
            event = session.get(Experience, event_id)
            event.min_capacity = 2
            for user_id in users:
                session.get(User, user_id).interests = ["Café", "Música"]
            session.commit()
            service = MatchingAlgorithmService(session)
            dto = MatchingApplicationDTO(experience_id=event_id)
            first = service.apply_for_matching(users[0], dto)
            for _ in range(2):
                read = service.get_group_status(event_id, users[1])
                self.assertEqual(read.current_members, 1)
                self.assertFalse(read.is_member)
            second = service.apply_for_matching(users[1], dto)
            self.assertEqual(second.id, first.id)
            self.assertTrue(second.is_quorum_reached)
            service.apply_for_matching(users[1], dto)
            self.assertEqual(
                session.query(MatchingMember)
                .filter(MatchingMember.matching_group_id == first.id)
                .count(),
                2,
            )
            self.assertEqual(session.get(Experience, event_id).reserved_slots, 0)
            self.assertEqual(
                session.get(Experience, event_id).status, ExperienceStatusEnum.OPEN
            )
            notices = (
                session.query(Notification)
                .filter(Notification.experience_id == event_id)
                .all()
            )
            self.assertEqual({item.user_id for item in notices}, {host_id, *users})
            self.assertTrue(all(item.kind == "MATCHING_READY" for item in notices))
            own = next(item for item in notices if item.user_id == users[0])
            with self.assertRaises(HTTPException):
                NotificationService(session).mark_read(own.id, users[1])
            session.rollback()
            NotificationService(session).mark_read(own.id, users[0])
            self.assertIsNotNone(session.get(Notification, own.id).read_at)
            service.leave_group(event_id, users[0])
            self.assertEqual(
                service.get_group_status(event_id, users[1]).current_members, 1
            )

    def test_catalog_searches_feed_demand_once_per_session_window(self):
        event_id, _, _ = self.event()
        query = "uncovered-" + uuid4().hex
        zone = "zone-" + uuid4().hex
        with self.sessions() as session:
            filters = ExperienceFilterDTO(search=query, zone=zone)
            service = ExperienceService(session)
            for _ in range(2):
                self.assertEqual(
                    service.search_catalog(filters, "search-session-a").total, 0
                )
            later_page = ExperienceFilterDTO(search=query, zone=zone, page=2)
            service.search_catalog(later_page, "search-session-a")
            self.assertEqual(
                session.query(SearchLog).filter(SearchLog.query_text == query).count(),
                1,
            )
            service.search_catalog(filters, "search-session-b")
            insight = DemandPredictionService(session).get_zone_insights(zone)[0]
            self.assertEqual(insight.search_count, 2)
            self.assertIsNone(insight.suggested_price)
            self.assertIsNone(
                DemandPredictionService(session)
                .generate_ai_experience_suggestions(zone)[0]
                .confidence_score
            )

    def test_notifications_do_not_deadlock_with_a_waiting_buyer(self):
        """Expone el ciclo usuario/experiencia que aparece usando FOR UPDATE en usuarios."""
        from app.booking.repository.booking_repository import BookingRepository

        event_id, _, users = self.event()
        account_locked = Event()
        with (
            self.sessions() as publisher,
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            BookingRepository(publisher).lock_experience(event_id)

            def waiting_buyer():
                with self.sessions() as buyer:
                    buyer.execute(text("SET LOCAL lock_timeout = '4s'"))
                    repository = BookingRepository(buyer)
                    repository.lock_user(users[0])
                    account_locked.set()
                    repository.lock_experience(event_id)
                    buyer.commit()

            future = executor.submit(waiting_buyer)
            try:
                self.assertTrue(account_locked.wait(timeout=3))
                publisher.execute(text("SET LOCAL lock_timeout = '3s'"))
                NotificationService(publisher).stage(
                    event_id, {users[0]}, "TEST_CONCURRENCY", 0, "Aviso de integración"
                )
                publisher.commit()
            finally:
                publisher.rollback()
            future.result(timeout=5)

    def test_two_buyers_compete_for_last_slot(self):
        """Dos conexiones simultáneas producen una única retención del último cupo."""
        event_id, _, users = self.event()
        barrier = Barrier(2)

        def reserve(user_id):
            """Reserva desde una sesión PostgreSQL independiente."""
            with self.sessions() as session:
                barrier.wait(timeout=5)
                try:
                    BookingService(session).create_booking(
                        user_id, BookingCreateDTO(experience_id=event_id), str(uuid4())
                    )
                    return "ok"
                except HTTPException as error:
                    self.assertEqual(error.status_code, 409)
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve, users))
        self.assertEqual(sorted(results), ["conflict", "ok"])

    def test_expiry_releases_capacity_and_replay_is_idempotent(self):
        """La misma clave repite la reserva; vencerla libera un cupo para otro usuario."""
        event_id, _, users = self.event()
        key = str(uuid4())
        with self.sessions() as session:
            service = BookingService(session)
            first = service.create_booking(
                users[0], BookingCreateDTO(experience_id=event_id), key
            )
            replay = service.create_booking(
                users[0], BookingCreateDTO(experience_id=event_id), key
            )
            self.assertEqual(first.id, replay.id)
            booking = session.get(Booking, first.id)
            booking.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
            self.assertEqual(service.release_expired_holds(), 1)
            self.assertEqual(service.release_expired_holds(), 0)
            second = service.create_booking(
                users[1], BookingCreateDTO(experience_id=event_id), str(uuid4())
            )
            self.assertEqual(second.status, BookingStatusEnum.PENDING)

    def test_free_tickets_and_single_check_in(self):
        """Una reserva gratuita emite una entrada por cupo e impide repetir el ingreso."""
        event_id, host_id, users = self.event(price="0", capacity=2)
        with self.sessions() as session:
            service = BookingService(session)
            result = service.create_booking(
                users[0],
                BookingCreateDTO(experience_id=event_id, quantity=2),
                str(uuid4()),
            )
            self.assertEqual(result.status, BookingStatusEnum.PAID)
            self.assertEqual(len(result.tickets), 2)
            self.assertNotEqual(
                result.tickets[0].ticket_code, result.tickets[1].ticket_code
            )
            self.assertTrue(service.check_in(result.tickets[0].id, host_id).is_used)
            with self.assertRaises(HTTPException) as error:
                service.check_in(result.tickets[0].id, host_id)
            self.assertEqual(error.exception.status_code, 409)

    def test_logout_is_seen_by_a_different_session(self):
        """Un JWT revocado continúa revocado al usar otra sesión y otro objeto de servicio."""
        token = create_access_token(str(uuid4()))
        with self.sessions() as session:
            revoke_token(token, session)
        with self.sessions() as session:
            with self.assertRaises(HTTPException) as error:
                decode_token(token, session)
            self.assertEqual(error.exception.status_code, 401)

    def test_failed_role_assignment_does_not_leave_an_orphan_account(self):
        """Un fallo tras insertar el usuario revierte la cuenta y su rol dentro de SQL."""
        email = uuid4().hex + "@example.com"
        with self.sessions() as session:
            service = AuthService(session)
            with patch.object(
                service.user_repo,
                "assign_role",
                side_effect=RuntimeError("role assignment failed"),
            ):
                with self.assertRaises(RuntimeError):
                    service.register(
                        RegisterDTO(
                            first_name="Audit", email=email, password="password123"
                        )
                    )
        with self.sessions() as session:
            self.assertIsNone(session.query(User).filter(User.email == email).first())
