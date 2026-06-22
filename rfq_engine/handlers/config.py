# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import logging
from typing import Any, Dict, List, Optional

import boto3


class Config:
    """
    Centralized Configuration Class
    Manages shared configuration variables across the application.
    """

    _initialized: bool = False
    _logger: Optional[logging.Logger] = None
    _setting: Dict[str, Any] = {}

    # Backend selection: "dynamodb" (default) or "postgresql"
    DB_BACKEND: str = "dynamodb"

    # PostgreSQL session (only initialized when DB_BACKEND == "postgresql")
    db_session = None

    # Class attributes
    aws_lambda = None
    aws_sqs = None
    aws_s3 = None
    schemas = {}

    # Cache Configuration
    CACHE_TTL = 1800  # 30 minutes default TTL
    CACHE_ENABLED = True

    # Cache name patterns for different modules.
    # The "models" prefix points at the canonical DynamoDB layer; PG
    # repositories don't use ``@method_cache`` today and would route
    # through a different prefix once they do.
    CACHE_NAMES = {
        "models": "rfq_engine.models.dynamodb",
        "queries": "rfq_engine.queries",
    }

    # ------------------------------------------------------------------
    # Cache entity metadata (module paths, getters, cache key templates).
    #
    # Backend-aware: the cache layer in silvaengine_dynamodb_base reads
    # `module` + `getter` as a *cache namespace prefix* matching what
    # @method_cache decorators stamped on those functions. Each backend
    # therefore owns its own table here; ``get_cache_entity_config()``
    # picks the right one based on ``Config.DB_BACKEND``.
    #
    # The PostgreSQL repositories do not currently use ``@method_cache``,
    # so its config is intentionally empty and cache hooks no-op
    # cleanly. Populate ``CACHE_ENTITY_CONFIG_POSTGRESQL`` when PG repos
    # start caching their getters.
    # ------------------------------------------------------------------
    CACHE_ENTITY_CONFIG_DYNAMODB = {
        "request": {
            "module": "rfq_engine.models.dynamodb.request",
            "model_class": "RequestModel",
            "getter": "get_request",
            "list_resolver": "rfq_engine.queries.request.resolve_request_list",
            "cache_keys": ["context:partition_key", "key:request_uuid"],
        },
        "quote": {
            "module": "rfq_engine.models.dynamodb.quote",
            "model_class": "QuoteModel",
            "getter": "get_quote",
            "list_resolver": "rfq_engine.queries.quote.resolve_quote_list",
            "cache_keys": ["key:request_uuid", "key:quote_uuid"],
        },
        "quote_item": {
            "module": "rfq_engine.models.dynamodb.quote_item",
            "model_class": "QuoteItemModel",
            "getter": "get_quote_item",
            "list_resolver": "rfq_engine.queries.quote_item.resolve_quote_item_list",
            "cache_keys": ["key:quote_uuid", "key:quote_item_uuid"],
        },
        "segment": {
            "module": "rfq_engine.models.dynamodb.segment",
            "model_class": "SegmentModel",
            "getter": "get_segment",
            "list_resolver": "rfq_engine.queries.segment.resolve_segment_list",
            "cache_keys": ["context:partition_key", "key:segment_uuid"],
        },
        "segment_contact": {
            "module": "rfq_engine.models.dynamodb.segment_contact",
            "model_class": "SegmentContactModel",
            "getter": "get_segment_contact",
            "list_resolver": "rfq_engine.queries.segment_contact.resolve_segment_contact_list",
            "cache_keys": ["key:segment_uuid", "key:email"],
        },
        "item": {
            "module": "rfq_engine.models.dynamodb.item",
            "model_class": "ItemModel",
            "getter": "get_item",
            "list_resolver": "rfq_engine.queries.item.resolve_item_list",
            "cache_keys": ["context:partition_key", "key:item_uuid"],
        },
        "provider_item": {
            "module": "rfq_engine.models.dynamodb.provider_item",
            "model_class": "ProviderItemModel",
            "getter": "get_provider_item",
            "list_resolver": "rfq_engine.queries.provider_item.resolve_provider_item_list",
            "cache_keys": ["key:item_uuid", "key:provider_item_uuid"],
        },
        "provider_item_batch": {
            "module": "rfq_engine.models.dynamodb.provider_item_batches",
            "model_class": "ProviderItemBatchModel",
            "getter": "get_provider_item_batch",
            "list_resolver": "rfq_engine.queries.provider_item_batches.resolve_provider_item_batch_list",
            "cache_keys": ["key:provider_item_uuid", "key:batch_no"],
        },
        "item_price_tier": {
            "module": "rfq_engine.models.dynamodb.item_price_tier",
            "model_class": "ItemPriceTierModel",
            "getter": "get_item_price_tier",
            "list_resolver": "rfq_engine.queries.item_price_tier.resolve_item_price_tier_list",
            "cache_keys": ["key:item_uuid", "key:item_price_tier_uuid"],
        },
        "installment": {
            "module": "rfq_engine.models.dynamodb.installment",
            "model_class": "InstallmentModel",
            "getter": "get_installment",
            "list_resolver": "rfq_engine.queries.installment.resolve_installment_list",
            "cache_keys": ["key:quote_uuid", "key:installment_uuid"],
        },
        "file": {
            "module": "rfq_engine.models.dynamodb.file",
            "model_class": "FileModel",
            "getter": "get_file",
            "list_resolver": "rfq_engine.queries.file.resolve_file_list",
            "cache_keys": ["key:request_uuid", "key:file_uuid"],
        },
        "discount_prompt": {
            "module": "rfq_engine.models.dynamodb.discount_prompt",
            "model_class": "DiscountPromptModel",
            "getter": "get_discount_prompt",
            "list_resolver": "rfq_engine.queries.discount_prompt.resolve_discount_prompt_list",
            "cache_keys": ["context:partition_key", "key:discount_prompt_uuid"],
        },
        "fx_rate": {
            "module": "rfq_engine.models.dynamodb.fx_rate",
            "model_class": "FxRateModel",
            "getter": "get_fx_rate",
            "list_resolver": "rfq_engine.queries.fx_rate.resolve_fx_rate_list",
            "cache_keys": ["context:partition_key", "key:fx_rate_uuid"],
        },
        "cancellation_policy": {
            "module": "rfq_engine.models.dynamodb.cancellation_policy",
            "model_class": "CancellationPolicyModel",
            "getter": "get_cancellation_policy",
            "list_resolver": "rfq_engine.queries.cancellation_policy.resolve_cancellation_policy_list",
            "cache_keys": ["context:partition_key", "key:policy_uuid"],
        },
        "bundle": {
            "module": "rfq_engine.models.dynamodb.bundle",
            "model_class": "BundleModel",
            "getter": "get_bundle",
            "list_resolver": "rfq_engine.queries.bundle.resolve_bundle_list",
            "cache_keys": ["context:partition_key", "key:bundle_uuid"],
        },
        "bundle_component": {
            "module": "rfq_engine.models.dynamodb.bundle_component",
            "model_class": "BundleComponentModel",
            "getter": "get_bundle_component",
            "list_resolver": "rfq_engine.queries.bundle_component.resolve_bundle_component_list",
            "cache_keys": ["context:partition_key", "key:bundle_component_uuid"],
        },
        "item_catalog_ref": {
            "module": "rfq_engine.models.dynamodb.item_catalog_ref",
            "model_class": "ItemCatalogRefModel",
            "getter": "get_item_catalog_ref",
            "list_resolver": "rfq_engine.queries.item_catalog_ref.resolve_item_catalog_ref_list",
            "cache_keys": ["context:partition_key", "key:catalog_ref_uuid"],
        },
    }

    # PostgreSQL cache config — empty until PG repos opt into caching.
    CACHE_ENTITY_CONFIG_POSTGRESQL: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_cache_entity_config(cls) -> Dict[str, Dict[str, Any]]:
        """Return cache metadata for the active ``DB_BACKEND``."""
        if cls.DB_BACKEND == "postgresql":
            return cls.CACHE_ENTITY_CONFIG_POSTGRESQL
        return cls.CACHE_ENTITY_CONFIG_DYNAMODB

    # ------------------------------------------------------------------
    # Entity cache dependency relationships (cascading invalidation).
    #
    # Same backend split as above: PG repos don't currently cache list
    # resolvers, so the PG relationships table is empty and cascading
    # purges no-op on PostgreSQL.
    # ------------------------------------------------------------------
    CACHE_RELATIONSHIPS_DYNAMODB = {
        "request": [
            {
                "entity_type": "quote",
                "list_resolver": "resolve_quote_list",
                "module": "quote",
                "dependency_key": "request_uuid",
            },
            {
                "entity_type": "file",
                "list_resolver": "resolve_file_list",
                "module": "file",
                "dependency_key": "request_uuid",
            },
        ],
        "bundle": [
            {
                "entity_type": "bundle_component",
                "list_resolver": "resolve_bundle_component_list",
                "module": "bundle_component",
                "dependency_key": "bundle_uuid",
            },
        ],
        "quote": [
            {
                "entity_type": "quote_item",
                "list_resolver": "resolve_quote_item_list",
                "module": "quote_item",
                "dependency_key": "quote_uuid",
            },
            {
                "entity_type": "installment",
                "list_resolver": "resolve_installment_list",
                "module": "installment",
                "dependency_key": "quote_uuid",
            },
        ],
        "segment": [
            {
                "entity_type": "segment_contact",
                "list_resolver": "resolve_segment_contact_list",
                "module": "segment_contact",
                "dependency_key": "segment_uuid",
            },
            {
                "entity_type": "item_price_tier",
                "list_resolver": "resolve_item_price_tier_list",
                "module": "item_price_tier",
                "dependency_key": "segment_uuid",
            },
            {
                "entity_type": "discount_prompt",
                "list_resolver": "resolve_discount_prompt_list",
                "module": "discount_prompt",
                "dependency_key": "segment_uuid",
            },
        ],
        "item": [
            {
                "entity_type": "provider_item",
                "list_resolver": "resolve_provider_item_list",
                "module": "provider_item",
                "dependency_key": "item_uuid",
            },
            {
                "entity_type": "item_price_tier",
                "list_resolver": "resolve_item_price_tier_list",
                "module": "item_price_tier",
                "dependency_key": "item_uuid",
            },
            {
                "entity_type": "discount_prompt",
                "list_resolver": "resolve_discount_prompt_list",
                "module": "discount_prompt",
                "dependency_key": "item_uuid",
            },
        ],
        "provider_item": [
            {
                "entity_type": "provider_item_batch",
                "list_resolver": "resolve_provider_item_batch_list",
                "module": "provider_item_batches",
                "dependency_key": "provider_item_uuid",
            },
            {
                "entity_type": "item_price_tier",
                "list_resolver": "resolve_item_price_tier_list",
                "module": "item_price_tier",
                "dependency_key": "provider_item_uuid",
            },
            {
                "entity_type": "discount_prompt",
                "list_resolver": "resolve_discount_prompt_list",
                "module": "discount_prompt",
                "dependency_key": "provider_item_uuid",
            },
        ],
    }

    # PostgreSQL cascade relationships — empty until PG repos cache list
    # resolvers; populate in lock-step with CACHE_ENTITY_CONFIG_POSTGRESQL.
    CACHE_RELATIONSHIPS_POSTGRESQL: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def get_cache_relationships(cls) -> Dict[str, List[Dict[str, Any]]]:
        """Return cascade-invalidation relationships for the active backend."""
        if cls.DB_BACKEND == "postgresql":
            return cls.CACHE_RELATIONSHIPS_POSTGRESQL
        return cls.CACHE_RELATIONSHIPS_DYNAMODB

    # Public methods
    @classmethod
    def initialize(cls, logger: logging.Logger, setting: Dict[str, Any]) -> None:
        """
        Initialize configuration setting.

        Backend selection is driven by ``setting["db_backend"]``:
        - ``dynamodb`` (default): preserves current PynamoDB behavior.
        - ``postgresql``: uses SQLAlchemy scoped session for persistence.

        Args:
            logger (logging.Logger): Logger instance for logging.
            setting (Dict[str, Any]): Configuration dictionary.
        """
        try:
            cls._logger = logger
            cls._setting = dict(setting)
            cls._set_parameters(setting)

            # Read backend selection (deployment-time, not per request)
            cls.DB_BACKEND = str(setting.get("db_backend", "dynamodb")).lower()

            if cls.DB_BACKEND == "dynamodb":
                cls._initialize_aws_services(setting)
                cls._initialize_dynamodb_meta(setting)
            elif cls.DB_BACKEND == "postgresql":
                cls._initialize_optional_aws_services(setting)
                cls._initialize_db_session(setting)
            else:
                raise ValueError(f"Unknown db_backend: {cls.DB_BACKEND}")

            if setting.get("initialize_tables"):
                cls._initialize_tables(logger)
            cls._initialized = True
            logger.info(
                f"Configuration initialized successfully (db_backend={cls.DB_BACKEND})."
            )
        except Exception as e:
            logger.exception("Failed to initialize configuration.")
            raise e

    # Private methods
    @classmethod
    def _set_parameters(cls, setting: Dict[str, Any]) -> None:
        """
        Set application-level parameters.
        Args:
            setting (Dict[str, Any]): Configuration dictionary.
        """
        cls.source_email = setting.get("source_email")

        # Set cache enabled flag (defaults to True if not specified)
        if "cache_enabled" in setting:
            cls.CACHE_ENABLED = setting.get("cache_enabled", True)

    @classmethod
    def _initialize_aws_services(cls, setting: Dict[str, Any]) -> None:
        """
        Initialize AWS services, such as the S3 client.
        Args:
            setting (Dict[str, Any]): Configuration dictionary.
        """
        if all(
            setting.get(k)
            for k in ["region_name", "aws_access_key_id", "aws_secret_access_key"]
        ):
            aws_credentials = {
                "region_name": setting["region_name"],
                "aws_access_key_id": setting["aws_access_key_id"],
                "aws_secret_access_key": setting["aws_secret_access_key"],
            }
        else:
            aws_credentials = {}

        cls.aws_lambda = boto3.client("lambda", **aws_credentials)
        cls.aws_sqs = boto3.resource("sqs", **aws_credentials)
        cls.aws_s3 = boto3.client(
            "s3",
            **aws_credentials,
            config=boto3.session.Config(signature_version="s3v4"),
        )

    @classmethod
    def _initialize_dynamodb_meta(cls, setting: Dict[str, Any]) -> None:
        """Initialize PynamoDB BaseModel.Meta credentials from setting."""
        from silvaengine_dynamodb_base import BaseModel

        if (
            setting.get("region_name")
            and setting.get("aws_access_key_id")
            and setting.get("aws_secret_access_key")
        ):
            BaseModel.Meta.region = setting.get("region_name")
            BaseModel.Meta.aws_access_key_id = setting.get("aws_access_key_id")
            BaseModel.Meta.aws_secret_access_key = setting.get(
                "aws_secret_access_key"
            )

    @classmethod
    def _initialize_optional_aws_services(cls, setting: Dict[str, Any]) -> None:
        """
        Initialize AWS services (S3, SQS, Lambda) only if credentials are present.

        PostgreSQL backend does not require AWS credentials for persistence,
        but may still need S3 for file storage or Lambda/SQS for integrations.
        """
        if all(
            setting.get(k)
            for k in ["region_name", "aws_access_key_id", "aws_secret_access_key"]
        ):
            aws_credentials = {
                "region_name": setting["region_name"],
                "aws_access_key_id": setting["aws_access_key_id"],
                "aws_secret_access_key": setting["aws_secret_access_key"],
            }
            cls.aws_lambda = boto3.client("lambda", **aws_credentials)
            cls.aws_sqs = boto3.resource("sqs", **aws_credentials)
            cls.aws_s3 = boto3.client(
                "s3",
                **aws_credentials,
                config=boto3.session.Config(signature_version="s3v4"),
            )
        else:
            # PostgreSQL mode without AWS credentials — file/integration
            # features will be unavailable but persistence works.
            cls.aws_lambda = None
            cls.aws_sqs = None
            cls.aws_s3 = None

    @classmethod
    def _initialize_db_session(cls, setting: Dict[str, Any]) -> None:
        """
        Initialize the PostgreSQL database session using SQLAlchemy.

        Expected setting keys:
            db_host, db_port, db_user, db_password, db_schema
        """
        from urllib.parse import quote_plus

        from sqlalchemy import create_engine
        from sqlalchemy.orm import scoped_session, sessionmaker

        password = quote_plus(setting["db_password"])
        connection_string = (
            f"postgresql+psycopg2://{setting['db_user']}:{password}"
            f"@{setting['db_host']}:{setting['db_port']}/{setting['db_schema']}"
        )

        engine = create_engine(
            connection_string,
            pool_recycle=7200,
            pool_size=10,
            pool_pre_ping=True,
            echo=False,
        )

        cls.db_session = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=engine)
        )

    @classmethod
    def _initialize_tables(cls, logger: logging.Logger) -> None:
        """
        Initialize database tables by calling the backend-appropriate
        initialization method.
        """
        if cls.DB_BACKEND == "dynamodb":
            from ..models.dynamodb.utils import initialize_tables

            initialize_tables(logger)
        elif cls.DB_BACKEND == "postgresql":
            from ..models.postgresql.utils import initialize_tables as pg_init

            pg_init(logger, cls.db_session)

    @classmethod
    def get_cache_name(cls, module_type: str, model_name: str) -> str:
        """
        Generate standardized cache names.

        Args:
            module_type: 'models' or 'queries'
            model_name: Name of the model (e.g., 'request', 'quote')

        Returns:
            Standardized cache name string
        """
        base_name = cls.CACHE_NAMES.get(module_type, f"rfq_engine.{module_type}")
        return f"{base_name}.{model_name}"

    @classmethod
    def get_cache_ttl(cls) -> int:
        """Get the configured cache TTL."""
        return cls.CACHE_TTL

    @classmethod
    def is_cache_enabled(cls) -> bool:
        """Check if caching is enabled."""
        return cls.CACHE_ENABLED

    # ``get_cache_relationships`` is defined alongside the backend-aware
    # CACHE_RELATIONSHIPS_{DYNAMODB,POSTGRESQL} constants earlier in this
    # class. The helper below just queries one entity's child list using
    # whichever backend's table is active.

    @classmethod
    def get_entity_children(cls, entity_type: str) -> List[Dict[str, Any]]:
        """Get child entities for a specific entity type (active backend)."""
        return cls.get_cache_relationships().get(entity_type, [])

    @classmethod
    def get_setting(cls) -> Dict[str, Any]:
        """Return the setting dict stored at initialization time."""
        if not cls._initialized:
            raise RuntimeError("Config not initialized")
        return cls._setting

    @classmethod
    def get_logger(cls) -> logging.Logger:
        """Return the logger stored at initialization time."""
        if cls._logger:
            return cls._logger
        return logging.getLogger()
