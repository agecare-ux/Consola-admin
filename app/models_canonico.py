"""Modelos del esquema canónico `admin` (58 tablas).

ARCHIVO GENERADO. No editar a mano: se regenera con

    python -m scripts.generar_modelos

a partir de la base creada por modelo/agecare_admin_ddl.sql, que es la fuente de
verdad. Los modelos la reflejan, no al revés.

Quince clases llevan un nombre propio en vez del derivado de la tabla (AdminUser,
Ticket, TicketReply, ContentItem, Product, CaregiverProfile, ModerationItem,
SystemSetting, LegalVersion, Incident, Feature, ComponentState, LatencyWindow,
CriticalProcessState, AdminSession).

Casi todas las tablas llevan tenant_id, y el esquema impone por trigger reglas de
negocio (transiciones de estado, bloqueo optimista, inmutabilidad del registro de
auditoría, moderación única).
"""
from sqlalchemy import BigInteger, Boolean, CHAR, CheckConstraint, Column, Computed, Date, DateTime, ForeignKeyConstraint, Identity, Index, Integer, LargeBinary, Numeric, PrimaryKeyConstraint, SmallInteger, String, Table, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, JSONB
from typing import Any, Optional
import datetime
import decimal
import uuid

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarativa del esquema canónico."""


metadata = Base.metadata


class AdminRoles(Base):
    __tablename__ = 'admin_roles'
    __table_args__ = (
        PrimaryKeyConstraint('code', name='admin_roles_pkey'),
        {'comment': 'Roles internos del staff (spec 2.3): admin, analyst, support, '
                'editor, moderator.',
     'schema': 'admin'}
    )

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    requires_mfa_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    description: Mapped[Optional[str]] = mapped_column(String(300))

    admin_role_permissions: Mapped[list['AdminRolePermissions']] = relationship('AdminRolePermissions', back_populates='admin_roles')
    admin_users: Mapped[list['AdminUser']] = relationship('AdminUser', back_populates='admin_roles')


class AdminUsersHistory(Base):
    __tablename__ = 'admin_users_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='admin_users_history_op_check'),
        PrimaryKeyConstraint('history_id', name='admin_users_history_pkey'),
        Index('admin_users_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.admin_users (una fila por '
                'INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mfa_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    activated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    mfa_secret_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    locked_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)


class AppRoles(Base):
    __tablename__ = 'app_roles'
    __table_args__ = (
        PrimaryKeyConstraint('code', name='app_roles_pkey'),
        {'comment': 'Perfiles de usuario final (AppRole): family, caregiver, elder, '
                'doctor.',
     'schema': 'admin'}
    )

    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))

    features: Mapped[list['Feature']] = relationship('Feature', secondary='admin.feature_roles', back_populates='app_roles')
    feature_usage_daily: Mapped[list['FeatureUsageDaily']] = relationship('FeatureUsageDaily', back_populates='app_roles')
    feature_usage_events: Mapped[list['FeatureUsageEvents']] = relationship('FeatureUsageEvents', back_populates='app_roles')
    role_activity_window: Mapped[list['RoleActivityWindow']] = relationship('RoleActivityWindow', back_populates='app_roles')
    role_weekly_active: Mapped[list['RoleWeeklyActive']] = relationship('RoleWeeklyActive', back_populates='app_roles')
    feature_usage_window: Mapped[list['FeatureUsageWindow']] = relationship('FeatureUsageWindow', back_populates='app_roles')
    moderation_items: Mapped[list['ModerationItem']] = relationship('ModerationItem', back_populates='app_roles')
    support_tickets: Mapped[list['Ticket']] = relationship('Ticket', back_populates='app_roles')


class Components(Base):
    __tablename__ = 'components'
    __table_args__ = (
        PrimaryKeyConstraint('key', name='components_pkey'),
        {'comment': 'Componentes monitorizados (ComponentKey). Umbrales en '
                'system_settings ops_thresholds.<key>.',
     'schema': 'admin'}
    )

    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_async: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    latency_note: Mapped[Optional[str]] = mapped_column(String(200))

    ops_component_checks: Mapped[list['OpsComponentChecks']] = relationship('OpsComponentChecks', back_populates='components')
    ops_component_state: Mapped[list['ComponentState']] = relationship('ComponentState', back_populates='components')
    ops_latency_window: Mapped[list['LatencyWindow']] = relationship('LatencyWindow', back_populates='components')
    ops_request_stats: Mapped[list['OpsRequestStats']] = relationship('OpsRequestStats', back_populates='components')
    ops_incidents: Mapped[list['Incident']] = relationship('Incident', back_populates='components')
    ops_component_status_history: Mapped[list['OpsComponentStatusHistory']] = relationship('OpsComponentStatusHistory', back_populates='components')


class ContentItemsHistory(Base):
    __tablename__ = 'content_items_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='content_items_history_op_check'),
        PrimaryKeyConstraint('history_id', name='content_items_history_pkey'),
        Index('content_items_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.content_items (una fila por '
                'INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    tts_status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    tts_audio_url: Mapped[Optional[str]] = mapped_column(String(500))
    publish_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    archived_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)


class CriticalProcesses(Base):
    __tablename__ = 'critical_processes'
    __table_args__ = (
        PrimaryKeyConstraint('key', name='critical_processes_pkey'),
        {'comment': 'Procesos críticos de negocio medidos extremo a extremo (spec '
                '5.3).',
     'schema': 'admin'}
    )

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    chain: Mapped[str] = mapped_column(String(300), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))

    ops_critical_process_state: Mapped[list['CriticalProcessState']] = relationship('CriticalProcessState', back_populates='critical_processes')


class Feature(Base):
    __tablename__ = 'features'
    __table_args__ = (
        PrimaryKeyConstraint('key', name='features_pkey'),
        {'comment': 'Catálogo de funcionalidades instrumentadas; se administra por '
                'seed/migración (spec 7).',
     'schema': 'admin'}
    )

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_low: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'), comment='true en funciones de emergencia (SOS): uso bajo correcto por diseño.')
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    note: Mapped[Optional[str]] = mapped_column(String(300))

    app_roles: Mapped[list['AppRoles']] = relationship('AppRoles', secondary='admin.feature_roles', back_populates='features')
    feature_usage_daily: Mapped[list['FeatureUsageDaily']] = relationship('FeatureUsageDaily', back_populates='features')
    feature_usage_events: Mapped[list['FeatureUsageEvents']] = relationship('FeatureUsageEvents', back_populates='features')
    feature_usage_window: Mapped[list['FeatureUsageWindow']] = relationship('FeatureUsageWindow', back_populates='features')


class IncidentStatusTransitions(Base):
    __tablename__ = 'incident_status_transitions'
    __table_args__ = (
        PrimaryKeyConstraint('from_status', 'to_status', 'is_maintenance', name='incident_status_transitions_pkey'),
        {'comment': 'Transiciones válidas de incidente (spec 5.6), aplicadas por '
                'trigger.',
     'schema': 'admin'}
    )

    from_status: Mapped[str] = mapped_column(String(15), primary_key=True)
    to_status: Mapped[str] = mapped_column(String(15), primary_key=True)
    is_maintenance: Mapped[bool] = mapped_column(Boolean, primary_key=True)


class LegalVersionsHistory(Base):
    __tablename__ = 'legal_versions_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='legal_versions_history_op_check'),
        PrimaryKeyConstraint('history_id', name='legal_versions_history_pkey'),
        Index('legal_versions_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.legal_versions (una fila por '
                'INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)
    semver_major: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    semver_minor: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    changelog: Mapped[str] = mapped_column(String(2000), nullable=False)
    effective_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    requires_reacceptance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    semver: Mapped[Optional[str]] = mapped_column(String(10))
    published_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class MarketplaceCaregiversHistory(Base):
    __tablename__ = 'marketplace_caregivers_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='marketplace_caregivers_history_op_check'),
        PrimaryKeyConstraint('history_id', name='marketplace_caregivers_history_pkey'),
        Index('marketplace_caregivers_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.marketplace_caregivers (una fila '
                'por INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    caregiver_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    zone: Mapped[str] = mapped_column(String(80), nullable=False)
    specialties: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False)
    certifications_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    certifications_verified_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    rating_avg: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2))
    status_reason: Mapped[Optional[str]] = mapped_column(String(1000))
    internal_note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class MarketplaceProductsHistory(Base):
    __tablename__ = 'marketplace_products_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='marketplace_products_history_op_check'),
        PrimaryKeyConstraint('history_id', name='marketplace_products_history_pkey'),
        Index('marketplace_products_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.marketplace_products (una fila '
                'por INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    vendor: Mapped[str] = mapped_column(String(120), nullable=False)
    external_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    price_amount: Mapped[Optional[int]] = mapped_column(Integer)
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    archived_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)


class ModerationItemsHistory(Base):
    __tablename__ = 'moderation_items_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='moderation_items_history_op_check'),
        PrimaryKeyConstraint('history_id', name='moderation_items_history_pkey'),
        Index('moderation_items_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.moderation_items (una fila por '
                'INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    content_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_safety_report: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    author_role_code: Mapped[Optional[str]] = mapped_column(String(12))
    reported_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    reported_by_name: Mapped[Optional[str]] = mapped_column(String(120))
    report_reason: Mapped[Optional[str]] = mapped_column(String(300))
    reject_reason_code: Mapped[Optional[str]] = mapped_column(String(15))
    decision_note: Mapped[Optional[str]] = mapped_column(String(1000))
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class OpsIncidentsHistory(Base):
    __tablename__ = 'ops_incidents_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='ops_incidents_history_op_check'),
        PrimaryKeyConstraint('history_id', name='ops_incidents_history_pkey'),
        Index('ops_incidents_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.ops_incidents (una fila por '
                'INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[str] = mapped_column(String(15), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    is_maintenance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    auto_created: Mapped[bool] = mapped_column(Boolean, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    component_key: Mapped[Optional[str]] = mapped_column(String(30))
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)


class Plans(Base):
    __tablename__ = 'plans'
    __table_args__ = (
        CheckConstraint("billing_unit::text = ANY (ARRAY['none'::character varying, 'user'::character varying, 'family'::character varying, 'provider'::character varying]::text[])", name='plans_billing_unit_check'),
        PrimaryKeyConstraint('code', name='plans_pkey'),
        {'comment': 'Catálogo de planes (PlanCode). Precios vigentes en '
                'system_settings.plan_prices; congelados en metrics_plan_snapshot.',
     'schema': 'admin'}
    )

    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    billing_unit: Mapped[str] = mapped_column(String(12), nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))

    metrics_plan_snapshot: Mapped[list['MetricsPlanSnapshot']] = relationship('MetricsPlanSnapshot', back_populates='plans')
    support_tickets: Mapped[list['Ticket']] = relationship('Ticket', back_populates='plans')


class SettingDefinitions(Base):
    __tablename__ = 'setting_definitions'
    __table_args__ = (
        CheckConstraint("key::text ~ '^[a-z0-9_.]+$'::text", name='setting_definitions_key_check'),
        PrimaryKeyConstraint('key', name='setting_definitions_pkey'),
        {'comment': 'Catálogo de claves de configuración con su JSON Schema (spec 12). '
                'Sin DELETE por API.',
     'schema': 'admin'}
    )

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    value_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    default_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))

    system_settings: Mapped[list['SystemSetting']] = relationship('SystemSetting', back_populates='setting_definitions')


class SupportTicketsHistory(Base):
    __tablename__ = 'support_tickets_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='support_tickets_history_op_check'),
        PrimaryKeyConstraint('history_id', name='support_tickets_history_pkey'),
        Index('support_tickets_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.support_tickets (una fila por '
                'INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requester_name: Mapped[str] = mapped_column(String(120), nullable=False)
    requester_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    category_code: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    reopen_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    requester_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    requester_role_code: Mapped[Optional[str]] = mapped_column(String(12))
    requester_plan_code: Mapped[Optional[str]] = mapped_column(String(12))
    requester_context: Mapped[Optional[dict]] = mapped_column(JSONB)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    first_response_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)


class SystemSettingsHistory(Base):
    __tablename__ = 'system_settings_history'
    __table_args__ = (
        CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])", name='system_settings_history_op_check'),
        PrimaryKeyConstraint('history_id', name='system_settings_history_pkey'),
        Index('system_settings_history_tenant_time_idx', 'tenant_id', 'changed_at'),
        {'comment': 'Historial de versiones de admin.system_settings (una fila por '
                'INSERT/UPDATE/DELETE; changed_by = admin_users.id).',
     'schema': 'admin'}
    )

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    op: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    change_note: Mapped[Optional[str]] = mapped_column(String(500))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class Tenants(Base):
    __tablename__ = 'tenants'
    __table_args__ = (
        CheckConstraint('admin.is_valid_timezone(timezone::text)', name='tenants_timezone_valid'),
        CheckConstraint("code::text ~ '^[a-z0-9-]+$'::text", name='tenants_code_check'),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'::text", name='tenants_country_code_check'),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'::text", name='tenants_currency_code_check'),
        CheckConstraint("environment::text = ANY (ARRAY['production'::character varying, 'staging'::character varying, 'development'::character varying]::text[])", name='tenants_environment_check'),
        PrimaryKeyConstraint('id', name='tenants_pkey'),
        UniqueConstraint('code', name='tenants_code_key'),
        {'comment': 'Despliegue/mercado administrado por la consola. Aísla sus datos '
                'por RLS (tenant_id).',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False, comment='ISO 4217. Todos los importes (mrr_amount, price_amount) del tenant se expresan en esta moneda, en unidades enteras (CLP sin decimales).')
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, comment='Zona horaria de negocio con la que los jobs cortan los días y semanas (America/Santiago).')
    environment: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'production'::character varying"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    region: Mapped[Optional[str]] = mapped_column(String(60))

    admin_users: Mapped[list['AdminUser']] = relationship('AdminUser', back_populates='tenant')
    feature_usage_daily: Mapped[list['FeatureUsageDaily']] = relationship('FeatureUsageDaily', back_populates='tenant')
    feature_usage_events: Mapped[list['FeatureUsageEvents']] = relationship('FeatureUsageEvents', back_populates='tenant')
    job_runs: Mapped[list['JobRuns']] = relationship('JobRuns', back_populates='tenant')
    metrics_daily_users: Mapped[list['MetricsDailyUsers']] = relationship('MetricsDailyUsers', back_populates='tenant')
    metrics_funnel_snapshot: Mapped[list['MetricsFunnelSnapshot']] = relationship('MetricsFunnelSnapshot', back_populates='tenant')
    metrics_hourly_users: Mapped[list['MetricsHourlyUsers']] = relationship('MetricsHourlyUsers', back_populates='tenant')
    metrics_plan_snapshot: Mapped[list['MetricsPlanSnapshot']] = relationship('MetricsPlanSnapshot', back_populates='tenant')
    ops_component_checks: Mapped[list['OpsComponentChecks']] = relationship('OpsComponentChecks', back_populates='tenant')
    ops_component_state: Mapped[list['ComponentState']] = relationship('ComponentState', back_populates='tenant')
    ops_critical_process_state: Mapped[list['CriticalProcessState']] = relationship('CriticalProcessState', back_populates='tenant')
    ops_latency_window: Mapped[list['LatencyWindow']] = relationship('LatencyWindow', back_populates='tenant')
    ops_request_stats: Mapped[list['OpsRequestStats']] = relationship('OpsRequestStats', back_populates='tenant')
    role_activity_window: Mapped[list['RoleActivityWindow']] = relationship('RoleActivityWindow', back_populates='tenant')
    role_weekly_active: Mapped[list['RoleWeeklyActive']] = relationship('RoleWeeklyActive', back_populates='tenant')
    store_downloads_daily: Mapped[list['StoreDownloadsDaily']] = relationship('StoreDownloadsDaily', back_populates='tenant')
    support_metrics_daily: Mapped[list['SupportMetricsDaily']] = relationship('SupportMetricsDaily', back_populates='tenant')
    tenant_counters: Mapped[list['TenantCounters']] = relationship('TenantCounters', back_populates='tenant')
    admin_invitations: Mapped[list['AdminInvitations']] = relationship('AdminInvitations', back_populates='tenant')
    admin_login_attempts: Mapped[list['AdminLoginAttempts']] = relationship('AdminLoginAttempts', back_populates='tenant')
    admin_sessions: Mapped[list['AdminSession']] = relationship('AdminSession', back_populates='tenant')
    audit_log: Mapped[list['AuditLog']] = relationship('AuditLog', back_populates='tenant')
    content_items: Mapped[list['ContentItem']] = relationship('ContentItem', back_populates='tenant')
    feature_usage_window: Mapped[list['FeatureUsageWindow']] = relationship('FeatureUsageWindow', back_populates='tenant')
    legal_versions: Mapped[list['LegalVersion']] = relationship('LegalVersion', back_populates='tenant')
    marketplace_caregivers: Mapped[list['CaregiverProfile']] = relationship('CaregiverProfile', back_populates='tenant')
    marketplace_products: Mapped[list['Product']] = relationship('Product', back_populates='tenant')
    moderation_escalations: Mapped[list['ModerationEscalations']] = relationship('ModerationEscalations', back_populates='tenant')
    moderation_items: Mapped[list['ModerationItem']] = relationship('ModerationItem', back_populates='tenant')
    ops_incidents: Mapped[list['Incident']] = relationship('Incident', back_populates='tenant')
    support_tickets: Mapped[list['Ticket']] = relationship('Ticket', back_populates='tenant')
    system_settings: Mapped[list['SystemSetting']] = relationship('SystemSetting', back_populates='tenant')
    ops_component_status_history: Mapped[list['OpsComponentStatusHistory']] = relationship('OpsComponentStatusHistory', back_populates='tenant')
    support_csat_surveys: Mapped[list['SupportCsatSurveys']] = relationship('SupportCsatSurveys', back_populates='tenant')
    support_ticket_replies: Mapped[list['TicketReply']] = relationship('TicketReply', back_populates='tenant')


class TicketCategories(Base):
    __tablename__ = 'ticket_categories'
    __table_args__ = (
        PrimaryKeyConstraint('code', name='ticket_categories_pkey'),
        {'schema': 'admin'}
    )

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))

    support_tickets: Mapped[list['Ticket']] = relationship('Ticket', back_populates='ticket_categories')


class TicketStatusTransitions(Base):
    __tablename__ = 'ticket_status_transitions'
    __table_args__ = (
        PrimaryKeyConstraint('from_status', 'to_status', name='ticket_status_transitions_pkey'),
        {'comment': 'Transiciones válidas de ticket (spec 8.4), aplicadas por trigger.',
     'schema': 'admin'}
    )

    from_status: Mapped[str] = mapped_column(String(15), primary_key=True)
    to_status: Mapped[str] = mapped_column(String(15), primary_key=True)


class AdminRolePermissions(Base):
    __tablename__ = 'admin_role_permissions'
    __table_args__ = (
        CheckConstraint("access::text = ANY (ARRAY['read'::character varying, 'write'::character varying]::text[])", name='admin_role_permissions_access_check'),
        CheckConstraint("module::text = ANY (ARRAY['metrics'::character varying, 'ops'::character varying, 'support'::character varying, 'content'::character varying, 'marketplace'::character varying, 'moderation'::character varying, 'settings'::character varying, 'legal'::character varying, 'staff'::character varying, 'audit'::character varying]::text[])", name='admin_role_permissions_module_check'),
        ForeignKeyConstraint(['role_code'], ['admin.admin_roles.code'], name='admin_role_permissions_role_code_fkey'),
        PrimaryKeyConstraint('role_code', 'module', name='admin_role_permissions_pkey'),
        {'comment': 'Matriz de permisos por módulo (spec 2.3). read = L, write = E; '
                'sin fila = sin acceso.',
     'schema': 'admin'}
    )

    role_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    module: Mapped[str] = mapped_column(String(30), primary_key=True)
    access: Mapped[str] = mapped_column(String(5), nullable=False)

    admin_roles: Mapped['AdminRoles'] = relationship('AdminRoles', back_populates='admin_role_permissions')


class AdminUser(Base):
    __tablename__ = 'admin_users'
    __table_args__ = (
        CheckConstraint('NOT mfa_enabled OR mfa_secret_enc IS NOT NULL', name='admin_users_mfa_secret_ck'),
        CheckConstraint('activated_at IS NULL OR password_hash IS NOT NULL', name='admin_users_activated_ck'),
        CheckConstraint("email ~* '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'::citext", name='admin_users_email_check'),
        CheckConstraint('failed_attempts >= 0', name='admin_users_failed_attempts_check'),
        CheckConstraint('length(full_name::text) >= 2 AND length(full_name::text) <= 120', name='admin_users_full_name_check'),
        ForeignKeyConstraint(['created_by'], ['admin.admin_users.id'], name='admin_users_created_by_fkey'),
        ForeignKeyConstraint(['role_code'], ['admin.admin_roles.code'], name='admin_users_role_code_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='admin_users_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='admin_users_pkey'),
        UniqueConstraint('tenant_id', 'email', name='admin_users_email_tenant_uq'),
        Index('admin_users_search_idx', postgresql_ops={"((full_name::text || ' '::text) || email::text)": 'gin_trgm_ops'}, postgresql_using='gin'),
        Index('admin_users_tenant_role_idx', 'tenant_id', 'role_code', 'is_active'),
        {'comment': 'Cuentas del personal de Wellq Co (spec 3). Separadas de los '
                'usuarios de la app.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    mfa_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), comment='Argon2id. NULL = cuenta pendiente de activación (login → ADMIN_DISABLED).')
    activated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    mfa_secret_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, comment='Secreto TOTP cifrado por la aplicación (Key Vault). Nunca en claro ni en audit_log.')
    locked_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='Bloqueo de 15 min tras 5 intentos fallidos en 10 min (spec 3.1).')
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', remote_side=[id], back_populates='admin_users_reverse')
    admin_users_reverse: Mapped[list['AdminUser']] = relationship('AdminUser', remote_side=[created_by], back_populates='admin_users')
    admin_roles: Mapped['AdminRoles'] = relationship('AdminRoles', back_populates='admin_users')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='admin_users')
    admin_invitations_admin: Mapped[list['AdminInvitations']] = relationship('AdminInvitations', foreign_keys='[AdminInvitations.admin_id]', back_populates='admin')
    admin_invitations_created_by: Mapped[list['AdminInvitations']] = relationship('AdminInvitations', foreign_keys='[AdminInvitations.created_by]', back_populates='admin_users')
    admin_login_attempts: Mapped[list['AdminLoginAttempts']] = relationship('AdminLoginAttempts', back_populates='admin')
    admin_sessions: Mapped[list['AdminSession']] = relationship('AdminSession', back_populates='admin')
    audit_log: Mapped[list['AuditLog']] = relationship('AuditLog', back_populates='actor')
    content_items_created_by: Mapped[list['ContentItem']] = relationship('ContentItem', foreign_keys='[ContentItem.created_by]', back_populates='admin_users')
    content_items_updated_by: Mapped[list['ContentItem']] = relationship('ContentItem', foreign_keys='[ContentItem.updated_by]', back_populates='admin_users_')
    legal_versions_created_by: Mapped[list['LegalVersion']] = relationship('LegalVersion', foreign_keys='[LegalVersion.created_by]', back_populates='admin_users')
    legal_versions_published_by: Mapped[list['LegalVersion']] = relationship('LegalVersion', foreign_keys='[LegalVersion.published_by]', back_populates='admin_users_')
    marketplace_caregivers: Mapped[list['CaregiverProfile']] = relationship('CaregiverProfile', back_populates='admin_users')
    marketplace_products_created_by: Mapped[list['Product']] = relationship('Product', foreign_keys='[Product.created_by]', back_populates='admin_users')
    marketplace_products_updated_by: Mapped[list['Product']] = relationship('Product', foreign_keys='[Product.updated_by]', back_populates='admin_users_')
    moderation_escalations: Mapped[list['ModerationEscalations']] = relationship('ModerationEscalations', back_populates='admin_users')
    moderation_items: Mapped[list['ModerationItem']] = relationship('ModerationItem', back_populates='admin_users')
    ops_incidents_created_by: Mapped[list['Incident']] = relationship('Incident', foreign_keys='[Incident.created_by]', back_populates='admin_users')
    ops_incidents_updated_by: Mapped[list['Incident']] = relationship('Incident', foreign_keys='[Incident.updated_by]', back_populates='admin_users_')
    support_tickets_assigned_to: Mapped[list['Ticket']] = relationship('Ticket', foreign_keys='[Ticket.assigned_to]', back_populates='admin_users')
    support_tickets_created_by: Mapped[list['Ticket']] = relationship('Ticket', foreign_keys='[Ticket.created_by]', back_populates='admin_users_')
    system_settings: Mapped[list['SystemSetting']] = relationship('SystemSetting', back_populates='admin_users')
    support_ticket_replies: Mapped[list['TicketReply']] = relationship('TicketReply', back_populates='author_admin')


t_feature_roles = Table(
    'feature_roles', Base.metadata,
    Column('feature_key', String(50), primary_key=True),
    Column('app_role_code', String(12), primary_key=True),
    ForeignKeyConstraint(['app_role_code'], ['admin.app_roles.code'], name='feature_roles_app_role_code_fkey'),
    ForeignKeyConstraint(['feature_key'], ['admin.features.key'], ondelete='CASCADE', name='feature_roles_feature_key_fkey'),
    PrimaryKeyConstraint('feature_key', 'app_role_code', name='feature_roles_pkey'),
    schema='admin',
    comment='Perfiles a los que aplica cada función. Sin fila = null (celda gris) en la matriz de adopción.'
)


class FeatureUsageDaily(Base):
    __tablename__ = 'feature_usage_daily'
    __table_args__ = (
        CheckConstraint('events >= unique_users', name='feature_usage_daily_check'),
        CheckConstraint('unique_users >= 0', name='feature_usage_daily_unique_users_check'),
        ForeignKeyConstraint(['app_role_code'], ['admin.app_roles.code'], name='feature_usage_daily_app_role_code_fkey'),
        ForeignKeyConstraint(['feature_key'], ['admin.features.key'], name='feature_usage_daily_feature_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='feature_usage_daily_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'day', 'feature_key', 'app_role_code', name='feature_usage_daily_pkey'),
        {'comment': 'Usuarios únicos por función, rol y día (spec 2.8), derivada de '
                'feature_usage_events.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    feature_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    app_role_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    unique_users: Mapped[int] = mapped_column(Integer, nullable=False)
    events: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    app_roles: Mapped['AppRoles'] = relationship('AppRoles', back_populates='feature_usage_daily')
    features: Mapped['Feature'] = relationship('Feature', back_populates='feature_usage_daily')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='feature_usage_daily')


class FeatureUsageEvents(Base):
    __tablename__ = 'feature_usage_events'
    __table_args__ = (
        CheckConstraint("platform::text = ANY (ARRAY['ios'::character varying, 'android'::character varying, 'web'::character varying]::text[])", name='feature_usage_events_platform_check'),
        ForeignKeyConstraint(['app_role_code'], ['admin.app_roles.code'], name='feature_usage_events_app_role_code_fkey'),
        ForeignKeyConstraint(['feature_key'], ['admin.features.key'], name='feature_usage_events_feature_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='feature_usage_events_tenant_id_fkey'),
        PrimaryKeyConstraint('event_id', 'occurred_at', name='feature_usage_events_pkey'),
        Index('feature_usage_events_feature_idx', 'tenant_id', 'occurred_at', 'feature_key'),
        Index('feature_usage_events_user_idx', 'tenant_id', 'user_id', 'occurred_at'),
        {'comment': 'Eventos crudos de uso emitidos por la app (spec 7). Particionada '
                'por mes; retención 13 meses. Solo INSERT.',
     'schema': 'admin'}
    )

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, comment='Referencia lógica a app.users.id (sin FK: otra BD/esquema).')
    app_role_code: Mapped[str] = mapped_column(String(12), nullable=False)
    feature_key: Mapped[str] = mapped_column(String(50), nullable=False)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    platform: Mapped[Optional[str]] = mapped_column(String(10))
    app_version: Mapped[Optional[str]] = mapped_column(String(20))

    app_roles: Mapped['AppRoles'] = relationship('AppRoles', back_populates='feature_usage_events')
    features: Mapped['Feature'] = relationship('Feature', back_populates='feature_usage_events')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='feature_usage_events')


class JobRuns(Base):
    __tablename__ = 'job_runs'
    __table_args__ = (
        CheckConstraint("(status::text = 'running'::text) = (finished_at IS NULL)", name='job_runs_finished_ck'),
        CheckConstraint("status::text = ANY (ARRAY['running'::character varying, 'succeeded'::character varying, 'failed'::character varying]::text[])", name='job_runs_status_check'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='job_runs_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='job_runs_pkey'),
        Index('job_runs_name_idx', 'job_name', 'started_at'),
        Index('job_runs_tenant_idx', 'tenant_id', 'job_name', 'status'),
        {'comment': 'Bitácora de jobs de agregación, monitor y mantenimiento: frescura '
                'de los datos y alerta de conectores caídos (spec 4.4).',
     'schema': 'admin'}
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    watermark: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    rows_affected: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[Optional[str]] = mapped_column(Text)

    tenant: Mapped[Optional['Tenants']] = relationship('Tenants', back_populates='job_runs')


class MetricsDailyUsers(Base):
    __tablename__ = 'metrics_daily_users'
    __table_args__ = (
        CheckConstraint('active_users_eod >= 0', name='metrics_daily_users_active_users_eod_check'),
        CheckConstraint('cancellations >= 0', name='metrics_daily_users_cancellations_check'),
        CheckConstraint('churned_users >= 0', name='metrics_daily_users_churned_users_check'),
        CheckConstraint('downloads >= 0', name='metrics_daily_users_downloads_check'),
        CheckConstraint('mrr_amount >= 0', name='metrics_daily_users_mrr_amount_check'),
        CheckConstraint('paying_users_eod >= 0', name='metrics_daily_users_paying_users_eod_check'),
        CheckConstraint('signups >= 0', name='metrics_daily_users_signups_check'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='metrics_daily_users_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'day', name='metrics_daily_users_pkey'),
        {'comment': 'Serie diaria de Uso comercial (spec 4). Job 03:00 consolida el '
                'día anterior (is_final); job horario refresca el día en curso.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    signups: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    cancellations: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    churned_users: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='Bajas explícitas + inactivos según churn_definition (system_settings).')
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    active_users_eod: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    paying_users_eod: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    mrr_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('0'), comment='MRR al cierre del día en la moneda del tenant (CLP en Chile).')
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='metrics_daily_users')


class MetricsFunnelSnapshot(Base):
    __tablename__ = 'metrics_funnel_snapshot'
    __table_args__ = (
        CheckConstraint('accounts_total >= 0', name='metrics_funnel_snapshot_accounts_total_check'),
        CheckConstraint('active_30d >= 0', name='metrics_funnel_snapshot_active_30d_check'),
        CheckConstraint('downloads_total >= 0', name='metrics_funnel_snapshot_downloads_total_check'),
        CheckConstraint('paying >= 0', name='metrics_funnel_snapshot_paying_check'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='metrics_funnel_snapshot_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'as_of', name='metrics_funnel_snapshot_pkey'),
        {'comment': 'Embudo acumulado a la fecha (spec 4.4).', 'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    as_of: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    downloads_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    accounts_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    active_30d: Mapped[int] = mapped_column(Integer, nullable=False)
    paying: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='metrics_funnel_snapshot')


class MetricsHourlyUsers(Base):
    __tablename__ = 'metrics_hourly_users'
    __table_args__ = (
        CheckConstraint('cancellations >= 0', name='metrics_hourly_users_cancellations_check'),
        CheckConstraint("date_trunc('hour'::text, ts_hour) = ts_hour", name='metrics_hourly_users_ts_hour_check'),
        CheckConstraint('signups >= 0', name='metrics_hourly_users_signups_check'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='metrics_hourly_users_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'ts_hour', name='metrics_hourly_users_pkey'),
        {'comment': 'Buckets horarios para el periodo today (spec 4.2). Retención 7 '
                'días.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    ts_hour: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True)
    signups: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    cancellations: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='metrics_hourly_users')


class MetricsPlanSnapshot(Base):
    __tablename__ = 'metrics_plan_snapshot'
    __table_args__ = (
        CheckConstraint('monthly_churn >= 0::numeric AND monthly_churn <= 1::numeric', name='metrics_plan_snapshot_monthly_churn_check'),
        CheckConstraint('mrr_amount >= 0', name='metrics_plan_snapshot_mrr_amount_check'),
        CheckConstraint('price_amount >= 0', name='metrics_plan_snapshot_price_amount_check'),
        CheckConstraint('users >= 0', name='metrics_plan_snapshot_users_check'),
        ForeignKeyConstraint(['plan_code'], ['admin.plans.code'], name='metrics_plan_snapshot_plan_code_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='metrics_plan_snapshot_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'as_of', 'plan_code', name='metrics_plan_snapshot_pkey'),
        {'comment': 'Mezcla de planes (spec 4.3). Snapshot diario; price_amount '
                'congela el precio vigente.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    as_of: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    plan_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    users: Mapped[int] = mapped_column(Integer, nullable=False)
    mrr_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('0'))
    monthly_churn: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 5), nullable=False, server_default=text('0'))
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    price_amount: Mapped[Optional[int]] = mapped_column(Integer)

    plans: Mapped['Plans'] = relationship('Plans', back_populates='metrics_plan_snapshot')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='metrics_plan_snapshot')


class OpsComponentChecks(Base):
    __tablename__ = 'ops_component_checks'
    __table_args__ = (
        CheckConstraint('error_rate >= 0::numeric AND error_rate <= 1::numeric', name='ops_component_checks_error_rate_check'),
        CheckConstraint('latency_ms >= 0', name='ops_component_checks_latency_ms_check'),
        ForeignKeyConstraint(['component_key'], ['admin.components.key'], name='ops_component_checks_component_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_component_checks_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'component_key', 'checked_at', name='ops_component_checks_pkey'),
        {'comment': 'Health checks cada 60 s (spec 2.8). Particionada por día; '
                'retención 90 días.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    component_key: Mapped[str] = mapped_column(String(30), primary_key=True)
    checked_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 5))
    detail: Mapped[Optional[str]] = mapped_column(String(300))

    components: Mapped['Components'] = relationship('Components', back_populates='ops_component_checks')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ops_component_checks')


class ComponentState(Base):
    __tablename__ = 'ops_component_state'
    __table_args__ = (
        CheckConstraint('consecutive_breaches >= 0', name='ops_component_state_consecutive_breaches_check'),
        CheckConstraint('consecutive_failures >= 0', name='ops_component_state_consecutive_failures_check'),
        CheckConstraint('latency_p50_ms >= 0', name='ops_component_state_latency_p50_ms_check'),
        CheckConstraint('latency_p95_ms >= 0', name='ops_component_state_latency_p95_ms_check'),
        CheckConstraint("status::text = ANY (ARRAY['operational'::character varying, 'degraded'::character varying, 'outage'::character varying]::text[])", name='ops_component_state_status_check'),
        CheckConstraint('uptime_30d >= 0::numeric AND uptime_30d <= 1::numeric', name='ops_component_state_uptime_30d_check'),
        ForeignKeyConstraint(['component_key'], ['admin.components.key'], name='ops_component_state_component_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_component_state_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'component_key', name='ops_component_state_pkey'),
        {'comment': 'Última foto de cada componente mantenida por el monitor (spec '
                '5.1). degraded tras 3 ciclos sobre umbral; outage tras 3 fallos.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    component_key: Mapped[str] = mapped_column(String(30), primary_key=True)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    status_since: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    consecutive_breaches: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    uptime_30d: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 5), nullable=False, server_default=text('1'))
    checked_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    latency_p50_ms: Mapped[Optional[int]] = mapped_column(Integer)
    latency_p95_ms: Mapped[Optional[int]] = mapped_column(Integer)
    note: Mapped[Optional[str]] = mapped_column(String(200))

    components: Mapped['Components'] = relationship('Components', back_populates='ops_component_state')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ops_component_state')


t_ops_critical_process_runs = Table(
    'ops_critical_process_runs', Base.metadata,
    Column('tenant_id', Uuid, nullable=False),
    Column('process_key', String(40), nullable=False),
    Column('started_at', DateTime(True), nullable=False),
    Column('duration_seconds', Numeric(9, 3), nullable=False),
    Column('succeeded', Boolean, nullable=False),
    Column('is_synthetic', Boolean, nullable=False, server_default=text('false')),
    Column('trace_id', String(64)),
    CheckConstraint('duration_seconds >= 0::numeric', name='ops_critical_process_runs_duration_seconds_check'),
    ForeignKeyConstraint(['process_key'], ['admin.critical_processes.key'], name='ops_critical_process_runs_process_key_fkey'),
    ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_critical_process_runs_tenant_id_fkey'),
    Index('ops_critical_process_runs_idx', 'tenant_id', 'process_key', 'started_at'),
    schema='admin',
    comment='Ejecuciones reales y sintéticas de procesos críticos (spec 5.3). Particionada por día; retención 90 días.'
)


class CriticalProcessState(Base):
    __tablename__ = 'ops_critical_process_state'
    __table_args__ = (
        CheckConstraint('p95_seconds >= 0::numeric', name='ops_critical_process_state_p95_seconds_check'),
        CheckConstraint("status::text = ANY (ARRAY['operational'::character varying, 'degraded'::character varying, 'outage'::character varying]::text[])", name='ops_critical_process_state_status_check'),
        CheckConstraint('success_24h >= 0::numeric AND success_24h <= 1::numeric', name='ops_critical_process_state_success_24h_check'),
        ForeignKeyConstraint(['process_key'], ['admin.critical_processes.key'], name='ops_critical_process_state_process_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_critical_process_state_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'process_key', name='ops_critical_process_state_pkey'),
        {'comment': 'Estado calculado de cada proceso crítico (spec 5.3).',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    process_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    p95_seconds: Mapped[decimal.Decimal] = mapped_column(Numeric(9, 3), nullable=False)
    success_24h: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    based_on_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    last_run_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    critical_processes: Mapped['CriticalProcesses'] = relationship('CriticalProcesses', back_populates='ops_critical_process_state')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ops_critical_process_state')


class LatencyWindow(Base):
    __tablename__ = 'ops_latency_window'
    __table_args__ = (
        CheckConstraint('"window"::text = ANY (ARRAY[\'1h\'::character varying, \'24h\'::character varying, \'7d\'::character varying]::text[])', name='ops_latency_window_window_check'),
        CheckConstraint('p50_ms >= 0', name='ops_latency_window_p50_ms_check'),
        CheckConstraint('p95_ms >= p50_ms', name='ops_latency_window_check'),
        CheckConstraint('sample_count >= 0', name='ops_latency_window_sample_count_check'),
        ForeignKeyConstraint(['component_key'], ['admin.components.key'], name='ops_latency_window_component_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_latency_window_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'window', 'component_key', name='ops_latency_window_pkey'),
        {'comment': 'Percentiles agregados por ventana 1h/24h/7d desde '
                'ops_request_stats (spec 5.2). Refresco por minuto.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    window: Mapped[str] = mapped_column(String(4), primary_key=True)
    component_key: Mapped[str] = mapped_column(String(30), primary_key=True)
    p50_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    p95_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    components: Mapped['Components'] = relationship('Components', back_populates='ops_latency_window')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ops_latency_window')


class OpsRequestStats(Base):
    __tablename__ = 'ops_request_stats'
    __table_args__ = (
        CheckConstraint("date_trunc('minute'::text, minute) = minute", name='ops_request_stats_minute_check'),
        CheckConstraint('error_count >= 0 AND error_count <= sample_count', name='ops_request_stats_check2'),
        CheckConstraint('p50_ms >= 0', name='ops_request_stats_p50_ms_check'),
        CheckConstraint('p95_ms >= p50_ms', name='ops_request_stats_check'),
        CheckConstraint('p99_ms >= p95_ms', name='ops_request_stats_check1'),
        CheckConstraint('sample_count > 0', name='ops_request_stats_sample_count_check'),
        ForeignKeyConstraint(['component_key'], ['admin.components.key'], name='ops_request_stats_component_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_request_stats_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'component_key', 'minute', name='ops_request_stats_pkey'),
        {'comment': 'Percentiles de latencia por componente y minuto desde '
                'OpenTelemetry (spec 2.8). Particionada por día; retención 90 '
                'días.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    component_key: Mapped[str] = mapped_column(String(30), primary_key=True)
    minute: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True)
    p50_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    p95_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    p99_ms: Mapped[Optional[int]] = mapped_column(Integer)

    components: Mapped['Components'] = relationship('Components', back_populates='ops_request_stats')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ops_request_stats')


class RoleActivityWindow(Base):
    __tablename__ = 'role_activity_window'
    __table_args__ = (
        CheckConstraint('active_users >= 0', name='role_activity_window_active_users_check'),
        CheckConstraint('avg_session_seconds >= 0', name='role_activity_window_avg_session_seconds_check'),
        CheckConstraint('days_window >= 7 AND days_window <= 90', name='role_activity_window_days_window_check'),
        CheckConstraint('retention_30d >= 0::numeric AND retention_30d <= 1::numeric', name='role_activity_window_retention_30d_check'),
        CheckConstraint('sessions_per_week >= 0::numeric', name='role_activity_window_sessions_per_week_check'),
        ForeignKeyConstraint(['app_role_code'], ['admin.app_roles.code'], name='role_activity_window_app_role_code_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='role_activity_window_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'days_window', 'app_role_code', name='role_activity_window_pkey'),
        {'comment': 'Intensidad de uso por perfil (spec 6.1). Ventanas precalculadas '
                '7/14/30/60/90 días; la API elige la ventana ≥ days pedida.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    days_window: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    app_role_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False)
    growth_8w: Mapped[decimal.Decimal] = mapped_column(Numeric(7, 4), nullable=False, server_default=text('0'))
    sessions_per_week: Mapped[decimal.Decimal] = mapped_column(Numeric(7, 2), nullable=False, server_default=text('0'))
    avg_session_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    retention_30d: Mapped[decimal.Decimal] = mapped_column(Numeric(6, 5), nullable=False, server_default=text('0'))
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    app_roles: Mapped['AppRoles'] = relationship('AppRoles', back_populates='role_activity_window')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='role_activity_window')


class RoleWeeklyActive(Base):
    __tablename__ = 'role_weekly_active'
    __table_args__ = (
        CheckConstraint('EXTRACT(isodow FROM week_start) = 1::numeric', name='role_weekly_active_week_start_check'),
        CheckConstraint('active_users >= 0', name='role_weekly_active_active_users_check'),
        ForeignKeyConstraint(['app_role_code'], ['admin.app_roles.code'], name='role_weekly_active_app_role_code_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='role_weekly_active_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'week_start', 'app_role_code', name='role_weekly_active_pkey'),
        {'comment': 'Activos semanales por perfil (spec 6.2). week_start = lunes ISO.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    week_start: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    app_role_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    app_roles: Mapped['AppRoles'] = relationship('AppRoles', back_populates='role_weekly_active')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='role_weekly_active')


class StoreDownloadsDaily(Base):
    __tablename__ = 'store_downloads_daily'
    __table_args__ = (
        CheckConstraint('downloads >= 0', name='store_downloads_daily_downloads_check'),
        CheckConstraint("store::text = ANY (ARRAY['ios'::character varying, 'android'::character varying]::text[])", name='store_downloads_daily_store_check'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='store_downloads_daily_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'day', 'store', name='store_downloads_daily_pkey'),
        {'comment': 'Descargas diarias ingeridas de App Store Connect y Google Play '
                'Console (spec 2.8).',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    store: Mapped[str] = mapped_column(String(10), primary_key=True)
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    ingested_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='store_downloads_daily')


class SupportMetricsDaily(Base):
    __tablename__ = 'support_metrics_daily'
    __table_args__ = (
        CheckConstraint('csat_count >= 0', name='support_metrics_daily_csat_count_check'),
        CheckConstraint('csat_sum >= 0', name='support_metrics_daily_csat_sum_check'),
        CheckConstraint('first_response_seconds_avg >= 0', name='support_metrics_daily_first_response_seconds_avg_check'),
        CheckConstraint('resolution_seconds_avg >= 0', name='support_metrics_daily_resolution_seconds_avg_check'),
        CheckConstraint('tickets_closed >= 0', name='support_metrics_daily_tickets_closed_check'),
        CheckConstraint('tickets_created >= 0', name='support_metrics_daily_tickets_created_check'),
        CheckConstraint('tickets_resolved >= 0', name='support_metrics_daily_tickets_resolved_check'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='support_metrics_daily_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'day', name='support_metrics_daily_pkey'),
        {'comment': 'Agregado diario de soporte (spec 2.8 / 6.3). Los contadores por '
                'estado se leen en vivo de support_tickets.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    tickets_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    tickets_resolved: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    tickets_closed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    csat_sum: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    csat_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    first_response_seconds_avg: Mapped[Optional[int]] = mapped_column(Integer)
    resolution_seconds_avg: Mapped[Optional[int]] = mapped_column(Integer)

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='support_metrics_daily')


class TenantCounters(Base):
    __tablename__ = 'tenant_counters'
    __table_args__ = (
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='tenant_counters_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'counter_name', name='tenant_counters_pkey'),
        {'comment': 'Correlativos por tenant (ticket_number). Se incrementa con '
                'bloqueo de fila en el trigger.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    counter_name: Mapped[str] = mapped_column(String(40), primary_key=True)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('1'))

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='tenant_counters')


class AdminInvitations(Base):
    __tablename__ = 'admin_invitations'
    __table_args__ = (
        CheckConstraint('expires_at > created_at', name='admin_invitations_expiry_ck'),
        ForeignKeyConstraint(['admin_id'], ['admin.admin_users.id'], ondelete='CASCADE', name='admin_invitations_admin_id_fkey'),
        ForeignKeyConstraint(['created_by'], ['admin.admin_users.id'], name='admin_invitations_created_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='admin_invitations_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='admin_invitations_pkey'),
        UniqueConstraint('token_hash', name='admin_invitations_token_hash_key'),
        Index('admin_invitations_admin_idx', 'admin_id'),
        {'comment': 'Enlaces de activación de un solo uso, 24 h (spec 3.5). token_hash '
                '= SHA-256 del token enviado por correo.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    admin_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    used_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    admin: Mapped['AdminUser'] = relationship('AdminUser', foreign_keys=[admin_id], back_populates='admin_invitations_admin')
    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[created_by], back_populates='admin_invitations_created_by')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='admin_invitations')


class AdminLoginAttempts(Base):
    __tablename__ = 'admin_login_attempts'
    __table_args__ = (
        CheckConstraint("failure_code::text = ANY (ARRAY['INVALID_CREDENTIALS'::character varying, 'OTP_REQUIRED'::character varying, 'OTP_INVALID'::character varying, 'ADMIN_DISABLED'::character varying, 'ACCOUNT_LOCKED'::character varying]::text[])", name='admin_login_attempts_failure_code_check'),
        CheckConstraint('succeeded OR failure_code IS NOT NULL', name='admin_login_attempts_failure_ck'),
        ForeignKeyConstraint(['admin_id'], ['admin.admin_users.id'], ondelete='SET NULL', name='admin_login_attempts_admin_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='admin_login_attempts_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='admin_login_attempts_pkey'),
        Index('admin_login_attempts_lookup_idx', 'tenant_id', 'email', 'attempted_at'),
        {'comment': 'Intentos de login persistidos para el bloqueo progresivo (spec '
                '3.1). Retención 90 días (job).',
     'schema': 'admin'}
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempted_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    failure_code: Mapped[Optional[str]] = mapped_column(String(30))
    ip: Mapped[Optional[Any]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300))

    admin: Mapped[Optional['AdminUser']] = relationship('AdminUser', back_populates='admin_login_attempts')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='admin_login_attempts')


class AdminSession(Base):
    __tablename__ = 'admin_sessions'
    __table_args__ = (
        CheckConstraint('(revoked_at IS NULL) = (revoked_reason IS NULL)', name='admin_sessions_revoked_ck'),
        CheckConstraint("revoked_reason::text = ANY (ARRAY['logout'::character varying, 'rotated'::character varying, 'reuse_detected'::character varying, 'admin_disabled'::character varying, 'expired'::character varying]::text[])", name='admin_sessions_revoked_reason_check'),
        ForeignKeyConstraint(['admin_id'], ['admin.admin_users.id'], ondelete='CASCADE', name='admin_sessions_admin_id_fkey'),
        ForeignKeyConstraint(['rotated_from'], ['admin.admin_sessions.id'], name='admin_sessions_rotated_from_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='admin_sessions_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='admin_sessions_pkey'),
        UniqueConstraint('refresh_token_hash', name='admin_sessions_refresh_token_hash_key'),
        Index('admin_sessions_admin_idx', 'admin_id', 'revoked_at'),
        Index('admin_sessions_expiry_idx', 'expires_at'),
        Index('admin_sessions_family_idx', 'family_id'),
        {'comment': 'Refresh tokens rotatorios (12 h). Reusar un token rotado revoca '
                'toda la familia (spec 3.2).',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    admin_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, comment='Todas las rotaciones derivadas de un mismo login comparten family_id.')
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    rotated_from: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    revoked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    revoked_reason: Mapped[Optional[str]] = mapped_column(String(30))
    ip: Mapped[Optional[Any]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300))

    admin: Mapped['AdminUser'] = relationship('AdminUser', back_populates='admin_sessions')
    admin_sessions: Mapped[Optional['AdminSession']] = relationship('AdminSession', remote_side=[id], back_populates='admin_sessions_reverse')
    admin_sessions_reverse: Mapped[list['AdminSession']] = relationship('AdminSession', remote_side=[rotated_from], back_populates='admin_sessions')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='admin_sessions')


class AuditLog(Base):
    __tablename__ = 'audit_log'
    __table_args__ = (
        CheckConstraint("action::text ~ '^[a-z_]+\\.[a-z_]+$'::text", name='audit_log_action_check'),
        ForeignKeyConstraint(['actor_id'], ['admin.admin_users.id'], name='audit_log_actor_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='audit_log_tenant_id_fkey'),
        PrimaryKeyConstraint('id', 'created_at', name='audit_log_pkey'),
        Index('audit_log_action_idx', 'tenant_id', 'action', 'created_at'),
        Index('audit_log_actor_idx', 'tenant_id', 'actor_id', 'created_at'),
        Index('audit_log_entity_idx', 'tenant_id', 'entity_type', 'entity_id'),
        Index('audit_log_tenant_time_idx', 'tenant_id', 'created_at'),
        {'comment': 'Registro inmutable de acciones del staff (spec 14). Solo INSERT; '
                'particionada por mes; retención 24 meses.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False, comment='Acción tipificada modulo.verbo: ticket.update, settings.update, auth.login_failed…')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), primary_key=True, server_default=text('now()'))
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    actor_name: Mapped[Optional[str]] = mapped_column(String(120))
    actor_role: Mapped[Optional[str]] = mapped_column(String(20))
    entity_type: Mapped[Optional[str]] = mapped_column(String(40))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    before: Mapped[Optional[dict]] = mapped_column(JSONB, comment='Estado previo (diff) con campos sensibles enmascarados por la aplicación.')
    after: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip: Mapped[Optional[Any]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300))
    request_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    actor: Mapped[Optional['AdminUser']] = relationship('AdminUser', back_populates='audit_log')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='audit_log')


class ContentItem(Base):
    __tablename__ = 'content_items'
    __table_args__ = (
        CheckConstraint('cardinality(tags) <= 10', name='content_items_tags_check'),
        CheckConstraint("deleted_at IS NULL OR status::text <> 'published'::text", name='content_items_deleted_ck'),
        CheckConstraint('length(body) >= 10 AND length(body) <= 4000', name='content_items_body_check'),
        CheckConstraint('length(title::text) >= 3 AND length(title::text) <= 160', name='content_items_title_check'),
        CheckConstraint("status::text <> 'archived'::text OR archived_at IS NOT NULL", name='content_items_archived_ck'),
        CheckConstraint("status::text <> 'published'::text OR published_at IS NOT NULL AND tts_status::text = 'ready'::text", name='content_items_published_ck'),
        CheckConstraint("status::text = ANY (ARRAY['draft'::character varying, 'published'::character varying, 'archived'::character varying]::text[])", name='content_items_status_check'),
        CheckConstraint("tts_status::text = ANY (ARRAY['pending'::character varying, 'ready'::character varying, 'failed'::character varying]::text[])", name='content_items_tts_status_check'),
        CheckConstraint("type::text = ANY (ARRAY['joke'::character varying, 'news'::character varying]::text[])", name='content_items_type_check'),
        ForeignKeyConstraint(['created_by'], ['admin.admin_users.id'], name='content_items_created_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='content_items_tenant_id_fkey'),
        ForeignKeyConstraint(['updated_by'], ['admin.admin_users.id'], name='content_items_updated_by_fkey'),
        PrimaryKeyConstraint('id', name='content_items_pkey'),
        Index('content_items_schedule_idx', 'tenant_id', 'publish_at', postgresql_where="(((status)::text = 'draft'::text) AND (publish_at IS NOT NULL))"),
        Index('content_items_search_idx', postgresql_ops={"((title::text || ' '::text) || body)": 'gin_trgm_ops'}, postgresql_using='gin'),
        Index('content_items_tags_idx', 'tags', postgresql_using='gin'),
        Index('content_items_type_status_idx', 'tenant_id', 'type', 'status', postgresql_where='(deleted_at IS NULL)'),
        {'comment': 'Chistes y noticias curados (spec 9). El feed de la app lee status '
                '= published AND deleted_at IS NULL. Borrado lógico. Historial en '
                'content_items_history.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'draft'::character varying"))
    tts_status: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'pending'::character varying"))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tts_audio_url: Mapped[Optional[str]] = mapped_column(String(500))
    publish_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    archived_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    admin_users: Mapped['AdminUser'] = relationship('AdminUser', foreign_keys=[created_by], back_populates='content_items_created_by')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='content_items')
    admin_users_: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[updated_by], back_populates='content_items_updated_by')


class FeatureUsageWindow(Base):
    __tablename__ = 'feature_usage_window'
    __table_args__ = (
        CheckConstraint('days_window = ANY (ARRAY[7, 30, 90])', name='feature_usage_window_days_window_check'),
        CheckConstraint('role_active_users >= 0', name='feature_usage_window_role_active_users_check'),
        CheckConstraint('users >= 0', name='feature_usage_window_users_check'),
        ForeignKeyConstraint(['app_role_code'], ['admin.app_roles.code'], name='feature_usage_window_app_role_code_fkey'),
        ForeignKeyConstraint(['feature_key', 'app_role_code'], ['admin.feature_roles.feature_key', 'admin.feature_roles.app_role_code'], name='feature_usage_window_feature_key_app_role_code_fkey'),
        ForeignKeyConstraint(['feature_key'], ['admin.features.key'], name='feature_usage_window_feature_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='feature_usage_window_tenant_id_fkey'),
        PrimaryKeyConstraint('tenant_id', 'days_window', 'feature_key', 'app_role_code', name='feature_usage_window_pkey'),
        {'comment': 'Matriz de adopción (spec 7). Solo pares (función, rol) de '
                'feature_roles; ausencia de fila = null en la API.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    days_window: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    feature_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    app_role_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    users: Mapped[int] = mapped_column(Integer, nullable=False)
    role_active_users: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    adoption: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 5), Computed('\nCASE\n    WHEN (role_active_users > 0) THEN LEAST(((users)::numeric / (role_active_users)::numeric), (1)::numeric)\n    ELSE (0)::numeric\nEND', persisted=True), comment='Generada: users / role_active_users (0–1).')

    app_roles: Mapped['AppRoles'] = relationship('AppRoles', back_populates='feature_usage_window')
    features: Mapped['Feature'] = relationship('Feature', back_populates='feature_usage_window')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='feature_usage_window')


class LegalVersion(Base):
    __tablename__ = 'legal_versions'
    __table_args__ = (
        CheckConstraint("doc_type::text = ANY (ARRAY['terms'::character varying, 'privacy'::character varying]::text[])", name='legal_versions_doc_type_check'),
        CheckConstraint('length(changelog::text) >= 10', name='legal_versions_changelog_check'),
        CheckConstraint('length(content_md) >= 100', name='legal_versions_content_md_check'),
        CheckConstraint('semver_major >= 0', name='legal_versions_semver_major_check'),
        CheckConstraint('semver_minor >= 0', name='legal_versions_semver_minor_check'),
        CheckConstraint("status::text = 'draft'::text OR published_by IS NOT NULL AND published_at IS NOT NULL", name='legal_versions_published_ck'),
        CheckConstraint("status::text = ANY (ARRAY['draft'::character varying, 'published'::character varying, 'superseded'::character varying]::text[])", name='legal_versions_status_check'),
        ForeignKeyConstraint(['created_by'], ['admin.admin_users.id'], name='legal_versions_created_by_fkey'),
        ForeignKeyConstraint(['published_by'], ['admin.admin_users.id'], name='legal_versions_published_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='legal_versions_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='legal_versions_pkey'),
        UniqueConstraint('tenant_id', 'doc_type', 'semver_major', 'semver_minor', name='legal_versions_semver_uq'),
        Index('legal_versions_current_idx', 'tenant_id', 'doc_type', 'effective_date', postgresql_where="((status)::text = 'published'::text)"),
        {'comment': 'Términos y política de privacidad versionados (spec 13). Nunca se '
                'borran: app.legal_acceptances referencia legal_versions.id. '
                'Historial en legal_versions_history.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)
    semver_major: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    semver_minor: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    changelog: Mapped[str] = mapped_column(String(2000), nullable=False)
    effective_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    requires_reacceptance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'draft'::character varying"), comment='draft → published (vigente desde effective_date) → superseded cuando otra versión posterior entra en vigor.')
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    semver: Mapped[Optional[str]] = mapped_column(String(10), Computed("((semver_major || '.'::text) || semver_minor)", persisted=True))
    published_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    admin_users: Mapped['AdminUser'] = relationship('AdminUser', foreign_keys=[created_by], back_populates='legal_versions_created_by')
    admin_users_: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[published_by], back_populates='legal_versions_published_by')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='legal_versions')


class CaregiverProfile(Base):
    __tablename__ = 'marketplace_caregivers'
    __table_args__ = (
        CheckConstraint('certifications_count >= 0', name='marketplace_caregivers_certifications_count_check'),
        CheckConstraint('certifications_verified_count >= 0 AND certifications_verified_count <= certifications_count', name='marketplace_caregivers_check'),
        CheckConstraint('length(internal_note) <= 2000', name='marketplace_caregivers_internal_note_check'),
        CheckConstraint('rating_avg >= 1::numeric AND rating_avg <= 5::numeric', name='marketplace_caregivers_rating_avg_check'),
        CheckConstraint('reviews_count >= 0', name='marketplace_caregivers_reviews_count_check'),
        CheckConstraint("status::text <> 'approved'::text OR certifications_verified_count >= 1", name='marketplace_caregivers_approved_ck'),
        CheckConstraint("status::text <> 'suspended'::text OR status_reason IS NOT NULL", name='marketplace_caregivers_suspended_ck'),
        CheckConstraint("status::text = 'pending'::text OR reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL", name='marketplace_caregivers_reviewed_ck'),
        CheckConstraint("status::text = ANY (ARRAY['pending'::character varying, 'approved'::character varying, 'suspended'::character varying]::text[])", name='marketplace_caregivers_status_check'),
        CheckConstraint('status_reason IS NULL OR length(status_reason::text) >= 10', name='marketplace_caregivers_status_reason_check'),
        ForeignKeyConstraint(['reviewed_by'], ['admin.admin_users.id'], name='marketplace_caregivers_reviewed_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='marketplace_caregivers_tenant_id_fkey'),
        PrimaryKeyConstraint('caregiver_id', name='marketplace_caregivers_pkey'),
        Index('marketplace_caregivers_search_idx', postgresql_ops={"((display_name::text || ' '::text) || email::text)": 'gin_trgm_ops'}, postgresql_using='gin'),
        Index('marketplace_caregivers_spec_idx', 'specialties', postgresql_using='gin'),
        Index('marketplace_caregivers_status_idx', 'tenant_id', 'status', 'submitted_at'),
        Index('marketplace_caregivers_zone_idx', 'tenant_id', 'zone'),
        {'comment': 'Estado de publicación en la vitrina de cada perfil de cuidadora '
                '(spec 10.1/10.2). caregiver_id = app.caregivers.id (referencia '
                'lógica). Campos descriptivos sincronizados desde la app. '
                'Historial en marketplace_caregivers_history.',
     'schema': 'admin'}
    )

    caregiver_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    zone: Mapped[str] = mapped_column(String(80), nullable=False)
    specialties: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]"))
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]"))
    certifications_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    certifications_verified_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'pending'::character varying"))
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    rating_avg: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2))
    status_reason: Mapped[Optional[str]] = mapped_column(String(1000))
    internal_note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', back_populates='marketplace_caregivers')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='marketplace_caregivers')


class Product(Base):
    __tablename__ = 'marketplace_products'
    __table_args__ = (
        CheckConstraint("external_url::text ~* '^https://'::text", name='marketplace_products_external_url_check'),
        CheckConstraint("image_url IS NULL OR image_url::text ~* '^https?://'::text", name='marketplace_products_image_url_check'),
        CheckConstraint('length(category::text) >= 2 AND length(category::text) <= 60', name='marketplace_products_category_check'),
        CheckConstraint('length(name::text) >= 3 AND length(name::text) <= 160', name='marketplace_products_name_check'),
        CheckConstraint('length(vendor::text) >= 2 AND length(vendor::text) <= 120', name='marketplace_products_vendor_check'),
        CheckConstraint('price_amount >= 0', name='marketplace_products_price_amount_check'),
        CheckConstraint("status::text <> 'archived'::text OR archived_at IS NOT NULL", name='marketplace_products_archived_ck'),
        CheckConstraint("status::text <> 'published'::text OR published_at IS NOT NULL", name='marketplace_products_published_ck'),
        CheckConstraint("status::text = ANY (ARRAY['draft'::character varying, 'published'::character varying, 'archived'::character varying]::text[])", name='marketplace_products_status_check'),
        ForeignKeyConstraint(['created_by'], ['admin.admin_users.id'], name='marketplace_products_created_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='marketplace_products_tenant_id_fkey'),
        ForeignKeyConstraint(['updated_by'], ['admin.admin_users.id'], name='marketplace_products_updated_by_fkey'),
        PrimaryKeyConstraint('id', name='marketplace_products_pkey'),
        Index('marketplace_products_search_idx', postgresql_ops={"((name::text || ' '::text) || vendor::text)": 'gin_trgm_ops'}, postgresql_using='gin'),
        Index('marketplace_products_status_idx', 'tenant_id', 'status', 'category'),
        {'comment': 'Catálogo de artículos de apoyo sin transacciones en v1 (spec '
                '10.3–10.5). Historial en marketplace_products_history.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    vendor: Mapped[str] = mapped_column(String(120), nullable=False)
    external_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'draft'::character varying"))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    price_amount: Mapped[Optional[int]] = mapped_column(Integer)
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    archived_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    admin_users: Mapped['AdminUser'] = relationship('AdminUser', foreign_keys=[created_by], back_populates='marketplace_products_created_by')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='marketplace_products')
    admin_users_: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[updated_by], back_populates='marketplace_products_updated_by')


class ModerationEscalations(Base):
    __tablename__ = 'moderation_escalations'
    __table_args__ = (
        CheckConstraint('is_open OR reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL', name='moderation_escalations_review_ck'),
        CheckConstraint('rejections_count >= 1', name='moderation_escalations_rejections_count_check'),
        ForeignKeyConstraint(['reviewed_by'], ['admin.admin_users.id'], name='moderation_escalations_reviewed_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='moderation_escalations_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='moderation_escalations_pkey'),
        Index('moderation_escalations_open_idx', 'tenant_id', 'is_open', 'triggered_at'),
        {'comment': 'Casos escalados al admin por el job de reglas (3 rechazos '
                'ofensivos del mismo autor en 90 días, spec 11.3).',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    rejections_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    window_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('90'))
    triggered_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    review_note: Mapped[Optional[str]] = mapped_column(Text)

    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', back_populates='moderation_escalations')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='moderation_escalations')


class ModerationItem(Base):
    __tablename__ = 'moderation_items'
    __table_args__ = (
        CheckConstraint("(status::text = 'pending'::text) = (decided_by IS NULL AND decided_at IS NULL)", name='moderation_items_decided_ck'),
        CheckConstraint("(status::text = 'rejected'::text) = (reject_reason_code IS NOT NULL)", name='moderation_items_reject_ck'),
        CheckConstraint('NOT is_safety_report OR reported_by_user_id IS NOT NULL', name='moderation_items_safety_ck'),
        CheckConstraint("item_type::text = ANY (ARRAY['review'::character varying, 'caregiver_profile'::character varying, 'photo'::character varying, 'chat_message'::character varying]::text[])", name='moderation_items_item_type_check'),
        CheckConstraint("reject_reason_code::text = ANY (ARRAY['offensive'::character varying, 'spam'::character varying, 'privacy'::character varying, 'off_topic'::character varying, 'other'::character varying]::text[])", name='moderation_items_reject_reason_code_check'),
        CheckConstraint("reject_reason_code::text IS DISTINCT FROM 'other'::text OR decision_note IS NOT NULL", name='moderation_items_other_ck'),
        CheckConstraint('reported_by_user_id IS NULL OR report_reason IS NOT NULL', name='moderation_items_report_ck'),
        CheckConstraint("status::text = ANY (ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying]::text[])", name='moderation_items_status_check'),
        ForeignKeyConstraint(['author_role_code'], ['admin.app_roles.code'], name='moderation_items_author_role_code_fkey'),
        ForeignKeyConstraint(['decided_by'], ['admin.admin_users.id'], name='moderation_items_decided_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='moderation_items_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='moderation_items_pkey'),
        UniqueConstraint('tenant_id', 'item_type', 'source_entity_id', name='moderation_items_source_uq'),
        Index('moderation_items_author_idx', 'tenant_id', 'author_user_id', 'decided_at', postgresql_where="((status)::text = 'rejected'::text)"),
        Index('moderation_items_queue_idx', 'tenant_id', 'is_safety_report', 'created_at', postgresql_where="((status)::text = 'pending'::text)"),
        Index('moderation_items_status_idx', 'tenant_id', 'status', 'decided_at'),
        {'comment': 'Cola única de moderación (spec 11): reseñas (previa) y contenido '
                'reportado. content_snapshot nunca guarda el binario ni URLs '
                'firmadas. Historial en moderation_items_history.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, comment='Referencia lógica al elemento de la app según item_type (app.reviews, app.photos, app.chat_messages, app.caregivers).')
    content_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_safety_report: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'pending'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    author_role_code: Mapped[Optional[str]] = mapped_column(String(12))
    reported_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    reported_by_name: Mapped[Optional[str]] = mapped_column(String(120))
    report_reason: Mapped[Optional[str]] = mapped_column(String(300))
    reject_reason_code: Mapped[Optional[str]] = mapped_column(String(15))
    decision_note: Mapped[Optional[str]] = mapped_column(String(1000))
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    app_roles: Mapped[Optional['AppRoles']] = relationship('AppRoles', back_populates='moderation_items')
    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', back_populates='moderation_items')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='moderation_items')


class Incident(Base):
    __tablename__ = 'ops_incidents'
    __table_args__ = (
        CheckConstraint("(status::text <> ALL (ARRAY['resolved'::character varying, 'completed'::character varying]::text[])) OR resolution IS NOT NULL AND resolved_at IS NOT NULL", name='ops_incidents_resolution_ck'),
        CheckConstraint('auto_created OR created_by IS NOT NULL', name='ops_incidents_creator_ck'),
        CheckConstraint('length(description) <= 4000', name='ops_incidents_description_check'),
        CheckConstraint('length(resolution) <= 2000', name='ops_incidents_resolution_check'),
        CheckConstraint('length(title::text) >= 5 AND length(title::text) <= 160', name='ops_incidents_title_check'),
        CheckConstraint('resolved_at IS NULL OR resolved_at >= started_at', name='ops_incidents_dates_ck'),
        CheckConstraint("severity::text = ANY (ARRAY['degraded'::character varying, 'outage'::character varying]::text[])", name='ops_incidents_severity_check'),
        CheckConstraint("status::text <> 'completed'::text OR is_maintenance", name='ops_incidents_completed_ck'),
        CheckConstraint("status::text = ANY (ARRAY['investigating'::character varying, 'observing'::character varying, 'resolved'::character varying, 'completed'::character varying]::text[])", name='ops_incidents_status_check'),
        ForeignKeyConstraint(['component_key'], ['admin.components.key'], name='ops_incidents_component_key_fkey'),
        ForeignKeyConstraint(['created_by'], ['admin.admin_users.id'], name='ops_incidents_created_by_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_incidents_tenant_id_fkey'),
        ForeignKeyConstraint(['updated_by'], ['admin.admin_users.id'], name='ops_incidents_updated_by_fkey'),
        PrimaryKeyConstraint('id', name='ops_incidents_pkey'),
        Index('ops_incidents_component_idx', 'tenant_id', 'component_key'),
        Index('ops_incidents_tenant_started_idx', 'tenant_id', 'started_at'),
        Index('ops_incidents_tenant_status_idx', 'tenant_id', 'status'),
        {'comment': 'Incidentes y mantenimientos (spec 5.4–5.6). Historial en '
                'ops_incidents_history.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[str] = mapped_column(String(15), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    is_maintenance: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    auto_created: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    component_key: Mapped[Optional[str]] = mapped_column(String(30))
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    components: Mapped[Optional['Components']] = relationship('Components', back_populates='ops_incidents')
    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[created_by], back_populates='ops_incidents_created_by')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ops_incidents')
    admin_users_: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[updated_by], back_populates='ops_incidents_updated_by')
    ops_component_status_history: Mapped[list['OpsComponentStatusHistory']] = relationship('OpsComponentStatusHistory', back_populates='incident')


class Ticket(Base):
    __tablename__ = 'support_tickets'
    __table_args__ = (
        CheckConstraint("(status::text <> ALL (ARRAY['resolved'::character varying, 'closed'::character varying]::text[])) OR resolved_at IS NOT NULL", name='support_tickets_resolved_ck'),
        CheckConstraint("(status::text = 'closed'::text) = (closed_at IS NOT NULL)", name='support_tickets_closed_ck'),
        CheckConstraint("channel::text <> 'console'::text OR created_by IS NOT NULL", name='support_tickets_console_ck'),
        CheckConstraint("channel::text = ANY (ARRAY['app'::character varying, 'email'::character varying, 'phone'::character varying, 'console'::character varying]::text[])", name='support_tickets_channel_check'),
        CheckConstraint('length(description) <= 8000', name='support_tickets_description_check'),
        CheckConstraint('length(subject::text) >= 5 AND length(subject::text) <= 160', name='support_tickets_subject_check'),
        CheckConstraint("priority::text = ANY (ARRAY['low'::character varying, 'medium'::character varying, 'high'::character varying, 'critical'::character varying]::text[])", name='support_tickets_priority_check'),
        CheckConstraint('reopen_count >= 0', name='support_tickets_reopen_count_check'),
        CheckConstraint("status::text = ANY (ARRAY['open'::character varying, 'in_progress'::character varying, 'waiting_user'::character varying, 'resolved'::character varying, 'closed'::character varying]::text[])", name='support_tickets_status_check'),
        ForeignKeyConstraint(['assigned_to'], ['admin.admin_users.id'], name='support_tickets_assigned_to_fkey'),
        ForeignKeyConstraint(['category_code'], ['admin.ticket_categories.code'], name='support_tickets_category_code_fkey'),
        ForeignKeyConstraint(['created_by'], ['admin.admin_users.id'], name='support_tickets_created_by_fkey'),
        ForeignKeyConstraint(['requester_plan_code'], ['admin.plans.code'], name='support_tickets_requester_plan_code_fkey'),
        ForeignKeyConstraint(['requester_role_code'], ['admin.app_roles.code'], name='support_tickets_requester_role_code_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='support_tickets_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='support_tickets_pkey'),
        UniqueConstraint('tenant_id', 'number', name='support_tickets_number_uq'),
        Index('support_tickets_assignee_idx', 'tenant_id', 'assigned_to', postgresql_where='(assigned_to IS NOT NULL)'),
        Index('support_tickets_category_idx', 'tenant_id', 'category_code', 'created_at'),
        Index('support_tickets_created_idx', 'tenant_id', 'created_at'),
        Index('support_tickets_priority_idx', 'tenant_id', 'priority', 'created_at'),
        Index('support_tickets_requester_idx', 'tenant_id', 'requester_user_id', postgresql_where='(requester_user_id IS NOT NULL)'),
        Index('support_tickets_search_idx', postgresql_ops={"((((number::text || ' '::text) || subject::text) || ' '::text) || requester_email::text)": 'gin_trgm_ops'}, postgresql_using='gin'),
        Index('support_tickets_status_idx', 'tenant_id', 'status', 'created_at'),
        {'comment': 'Cola de soporte (spec 8). number = correlativo visible por tenant '
                '(#1482). Historial en support_tickets_history.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requester_name: Mapped[str] = mapped_column(String(120), nullable=False)
    requester_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    category_code: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'medium'::character varying"))
    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'open'::character varying"))
    channel: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'app'::character varying"))
    reopen_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    requester_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, comment='Referencia lógica a app.users.id; NULL si el ticket se creó sin cuenta enlazada (confirm_unlinked).')
    requester_role_code: Mapped[Optional[str]] = mapped_column(String(12))
    requester_plan_code: Mapped[Optional[str]] = mapped_column(String(12))
    requester_context: Mapped[Optional[dict]] = mapped_column(JSONB, comment='Snapshot del contexto del solicitante: {patients:[{patient_id,display_name}], devices:[{platform,app_version,last_seen_at}]}.')
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    first_response_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='Fijado por trigger con la primera respuesta no interna de un admin; base del KPI de primera respuesta.')
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[assigned_to], back_populates='support_tickets_assigned_to')
    ticket_categories: Mapped['TicketCategories'] = relationship('TicketCategories', back_populates='support_tickets')
    admin_users_: Mapped[Optional['AdminUser']] = relationship('AdminUser', foreign_keys=[created_by], back_populates='support_tickets_created_by')
    plans: Mapped[Optional['Plans']] = relationship('Plans', back_populates='support_tickets')
    app_roles: Mapped[Optional['AppRoles']] = relationship('AppRoles', back_populates='support_tickets')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='support_tickets')
    support_csat_surveys: Mapped['SupportCsatSurveys'] = relationship('SupportCsatSurveys', uselist=False, back_populates='ticket')
    support_ticket_replies: Mapped[list['TicketReply']] = relationship('TicketReply', back_populates='ticket')


class SystemSetting(Base):
    __tablename__ = 'system_settings'
    __table_args__ = (
        CheckConstraint('change_note IS NULL OR length(change_note::text) >= 5', name='system_settings_change_note_check'),
        CheckConstraint('version >= 1', name='system_settings_version_check'),
        ForeignKeyConstraint(['key'], ['admin.setting_definitions.key'], name='system_settings_key_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='system_settings_tenant_id_fkey'),
        ForeignKeyConstraint(['updated_by'], ['admin.admin_users.id'], name='system_settings_updated_by_fkey'),
        PrimaryKeyConstraint('tenant_id', 'key', name='system_settings_pkey'),
        {'comment': 'Valor vigente de cada parámetro por tenant (spec 12). version = '
                'bloqueo optimista; cada cambio queda en system_settings_history.',
     'schema': 'admin'}
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    change_note: Mapped[Optional[str]] = mapped_column(String(500))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    setting_definitions: Mapped['SettingDefinitions'] = relationship('SettingDefinitions', back_populates='system_settings')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='system_settings')
    admin_users: Mapped[Optional['AdminUser']] = relationship('AdminUser', back_populates='system_settings')


class OpsComponentStatusHistory(Base):
    __tablename__ = 'ops_component_status_history'
    __table_args__ = (
        CheckConstraint("from_status::text = ANY (ARRAY['operational'::character varying, 'degraded'::character varying, 'outage'::character varying]::text[])", name='ops_component_status_history_from_status_check'),
        CheckConstraint("to_status::text = ANY (ARRAY['operational'::character varying, 'degraded'::character varying, 'outage'::character varying]::text[])", name='ops_component_status_history_to_status_check'),
        ForeignKeyConstraint(['component_key'], ['admin.components.key'], name='ops_component_status_history_component_key_fkey'),
        ForeignKeyConstraint(['incident_id'], ['admin.ops_incidents.id'], name='ops_component_status_history_incident_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='ops_component_status_history_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='ops_component_status_history_pkey'),
        Index('ops_component_status_history_idx', 'tenant_id', 'component_key', 'changed_at'),
        {'comment': 'Transiciones de estado por componente: base del uptime histórico '
                'y de los incidentes abiertos automáticamente.',
     'schema': 'admin'}
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    component_key: Mapped[str] = mapped_column(String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(String(15), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    from_status: Mapped[Optional[str]] = mapped_column(String(15))
    reason: Mapped[Optional[str]] = mapped_column(String(300))
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    components: Mapped['Components'] = relationship('Components', back_populates='ops_component_status_history')
    incident: Mapped[Optional['Incident']] = relationship('Incident', back_populates='ops_component_status_history')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ops_component_status_history')


class SupportCsatSurveys(Base):
    __tablename__ = 'support_csat_surveys'
    __table_args__ = (
        CheckConstraint('(responded_at IS NULL) = (score IS NULL)', name='support_csat_surveys_response_ck'),
        CheckConstraint('score >= 1 AND score <= 5', name='support_csat_surveys_score_check'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='support_csat_surveys_tenant_id_fkey'),
        ForeignKeyConstraint(['ticket_id'], ['admin.support_tickets.id'], ondelete='CASCADE', name='support_csat_surveys_ticket_id_fkey'),
        PrimaryKeyConstraint('id', name='support_csat_surveys_pkey'),
        UniqueConstraint('ticket_id', name='support_csat_surveys_ticket_id_key'),
        Index('support_csat_surveys_responded_idx', 'tenant_id', 'responded_at', postgresql_where='(responded_at IS NOT NULL)'),
        {'comment': 'Encuesta CSAT enviada al resolver (spec 8.4). Una por ticket.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    responded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    score: Mapped[Optional[int]] = mapped_column(SmallInteger)
    comment: Mapped[Optional[str]] = mapped_column(Text)

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='support_csat_surveys')
    ticket: Mapped['Ticket'] = relationship('Ticket', back_populates='support_csat_surveys')


class TicketReply(Base):
    __tablename__ = 'support_ticket_replies'
    __table_args__ = (
        CheckConstraint("NOT is_internal OR author_type::text = 'admin'::text", name='support_ticket_replies_internal_ck'),
        CheckConstraint("author_type::text = 'admin'::text AND author_admin_id IS NOT NULL OR author_type::text = 'user'::text AND author_user_id IS NOT NULL OR author_type::text = 'system'::text", name='support_ticket_replies_author_ck'),
        CheckConstraint("author_type::text = ANY (ARRAY['admin'::character varying, 'user'::character varying, 'system'::character varying]::text[])", name='support_ticket_replies_author_type_check'),
        CheckConstraint('length(body) >= 1 AND length(body) <= 8000', name='support_ticket_replies_body_check'),
        ForeignKeyConstraint(['author_admin_id'], ['admin.admin_users.id'], name='support_ticket_replies_author_admin_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['admin.tenants.id'], name='support_ticket_replies_tenant_id_fkey'),
        ForeignKeyConstraint(['ticket_id'], ['admin.support_tickets.id'], ondelete='CASCADE', name='support_ticket_replies_ticket_id_fkey'),
        PrimaryKeyConstraint('id', name='support_ticket_replies_pkey'),
        Index('support_ticket_replies_ticket_idx', 'ticket_id', 'created_at'),
        {'comment': 'Conversación del ticket (spec 8.5/8.6): respuestas de admin, '
                'mensajes del usuario y del sistema. Inmutable.',
     'schema': 'admin'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_type: Mapped[str] = mapped_column(String(10), nullable=False)
    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    author_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    author_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    author_admin: Mapped[Optional['AdminUser']] = relationship('AdminUser', back_populates='support_ticket_replies')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='support_ticket_replies')
    ticket: Mapped['Ticket'] = relationship('Ticket', back_populates='support_ticket_replies')
