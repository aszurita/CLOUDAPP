from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import DemoCustomer, DemoCustomerTransaction, Deployment, Environment, PlatformSetting, QueryPolicy, Service
from app.services.audit import record_audit_event


def seed_demo_data(db: Session) -> None:
    seed_platform_data(db)
    seed_phase2_data(db)


def seed_platform_data(db: Session) -> None:
    if db.query(Environment).count() > 0:
        return

    dev = Environment(code="DEV", name="Development", status="healthy", region="eastus")
    qa = Environment(code="QA", name="Quality Assurance", status="healthy", region="eastus")
    prod = Environment(code="PROD", name="Production", status="attention", region="eastus")
    db.add_all([dev, qa, prod])
    db.flush()

    api = Service(
        environment_id=dev.id,
        name="cloudops-api",
        service_type="FastAPI",
        status="healthy",
        version="0.1.0",
        health_url="/health",
        cost_estimate_usd=8,
    )
    portal = Service(
        environment_id=dev.id,
        name="cloudops-portal",
        service_type="React Static Web App",
        status="healthy",
        version="0.1.0",
        cost_estimate_usd=2,
    )
    postgres = Service(
        environment_id=prod.id,
        name="platform-postgresql",
        service_type="Azure PostgreSQL",
        status="attention",
        version="16",
        cost_estimate_usd=12,
    )
    db.add_all([api, portal, postgres])
    db.flush()

    db.add_all(
        [
            Deployment(service_id=api.id, commit_sha="local-seed", status="success", deployed_by="github-actions"),
            Deployment(service_id=portal.id, commit_sha="local-seed", status="success", deployed_by="github-actions"),
        ]
    )
    db.add_all(
        [
            PlatformSetting(key="ai_provider", value="openai", description="Default AI provider for phase 2."),
            PlatformSetting(key="openai_enabled", value="true", description="ChatGPT/OpenAI is required for phase 2."),
            PlatformSetting(key="databricks_enabled", value="false", description="Placeholder for phase 3 DataOps."),
            PlatformSetting(key="datahub_enabled", value="false", description="Placeholder for phase 4 catalog."),
        ]
    )
    db.commit()
    record_audit_event(db, "platform.seeded", "Demo platform data initialized.")


def seed_phase2_data(db: Session) -> None:
    if db.query(QueryPolicy).count() == 0:
        db.add_all(
            [
                QueryPolicy(
                    code="readonly_select_only",
                    description="Only SELECT statements are allowed in Query Governance.",
                    severity="high",
                ),
                QueryPolicy(
                    code="block_select_star",
                    description="SELECT * is blocked to prevent uncontrolled extraction.",
                    severity="medium",
                ),
                QueryPolicy(
                    code="require_limit",
                    description="Executable queries must include LIMIT.",
                    severity="medium",
                ),
                QueryPolicy(
                    code="block_internal_tables",
                    description="Internal platform tables are not queryable from the demo console.",
                    severity="high",
                ),
            ]
        )

    if db.query(DemoCustomer).count() == 0:
        segments = ["retail", "premium", "sme", "corporate"]
        account_types = ["checking", "savings", "credit"]
        customers = [
            DemoCustomer(
                customer_code=f"CUST-{index:04d}",
                segment=segments[index % len(segments)],
                email=f"customer{index:04d}@demo.local",
                account_type=account_types[index % len(account_types)],
                risk_score=(index * 7) % 100,
            )
            for index in range(1, 41)
        ]
        db.add_all(customers)
        db.flush()

        channels = ["web", "mobile", "branch", "atm"]
        categories = ["grocery", "travel", "utilities", "education", "health", "entertainment"]
        start_date = date(2026, 1, 1)
        transactions: list[DemoCustomerTransaction] = []
        for index in range(1, 401):
            customer = customers[index % len(customers)]
            amount = Decimal("12.50") + Decimal(index % 250) * Decimal("3.15")
            transactions.append(
                DemoCustomerTransaction(
                    customer_id=customer.id,
                    transaction_date=start_date + timedelta(days=index % 120),
                    transaction_amount=amount,
                    channel=channels[index % len(channels)],
                    status="approved" if index % 13 else "review",
                    merchant_category=categories[index % len(categories)],
                    risk_flag=index % 17 == 0 or customer.risk_score > 80,
                )
            )
        db.add_all(transactions)

    db.commit()
    record_audit_event(db, "phase2.seeded", "Query Governance and DBA Copilot demo data initialized.")
