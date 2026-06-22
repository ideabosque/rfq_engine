# -*- coding: utf-8 -*-
"""PostgreSQL repository for QuoteItem entity.

Implements the EntityRepository contract using SQLAlchemy queries
against the PostgreSQL QuoteItemModel. Ports the pricing logic from the
DynamoDB ``insert_update_quote_item`` so the PG backend produces the same
auto-calculated fields: ``price_per_uom`` (tier resolution), ``subtotal``
(with FX conversion), ``final_subtotal``, cancellation policy snapshot, and
parent quote totals roll-up.
"""
from __future__ import print_function

__author__ = "bibow"

import json
import traceback
from typing import Any, Dict, List, Optional

import pendulum
from graphene import ResolveInfo

from ....handlers.config import Config
from ....types.quote_item import QuoteItemListType, QuoteItemType
from ....utils.normalization import normalize_to_json
from ...postgresql.base import normalize_row
from ..base import EntityRepository
from ...postgresql.quote_item import QuoteItemModel


class QuoteItemPGRepository(EntityRepository):
    """PostgreSQL repository for QuoteItem entity."""

    @property
    def entity_type(self) -> str:
        return "quote_item"

    def get(self, **keys: Any) -> Optional[Dict[str, Any]]:
        quote_uuid = keys.get("quote_uuid")
        quote_item_uuid = keys.get("quote_item_uuid")
        if not quote_uuid or not quote_item_uuid:
            return None
        session = Config.db_session
        row = (
            session.query(QuoteItemModel)
            .filter(
                QuoteItemModel.quote_uuid == quote_uuid,
                QuoteItemModel.quote_item_uuid == quote_item_uuid,
            )
            .first()
        )
        return normalize_row(row) if row else None

    def count(self, **keys: Any) -> int:
        quote_uuid = keys.get("quote_uuid")
        quote_item_uuid = keys.get("quote_item_uuid")
        if not quote_uuid or not quote_item_uuid:
            return 0
        session = Config.db_session
        return (
            session.query(QuoteItemModel)
            .filter(
                QuoteItemModel.quote_uuid == quote_uuid,
                QuoteItemModel.quote_item_uuid == quote_item_uuid,
            )
            .count()
        )

    def list(self, info: ResolveInfo, **filters: Any) -> Any:
        """Return paginated quote item list matching the GraphQL connection shape."""
        from silvaengine_dynamodb_base import ListObjectType

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        page_number = filters.get("page_number", 1)
        limit = filters.get("limit", 10)
        quote_uuid = filters.get("quote_uuid")
        provider_item_uuid = filters.get("provider_item_uuid")
        item_uuid = filters.get("item_uuid")
        request_uuid = filters.get("request_uuid")
        status = filters.get("status")

        query = session.query(QuoteItemModel)
        if quote_uuid:
            query = query.filter(QuoteItemModel.quote_uuid == quote_uuid)
        if provider_item_uuid:
            query = query.filter(
                QuoteItemModel.provider_item_uuid == provider_item_uuid
            )
        if item_uuid:
            query = query.filter(QuoteItemModel.item_uuid == item_uuid)
        if request_uuid:
            query = query.filter(QuoteItemModel.request_uuid == request_uuid)
        if partition_key:
            query = query.filter(QuoteItemModel.partition_key == partition_key)

        total = query.count()
        offset = (page_number - 1) * limit
        rows = (
            query.order_by(QuoteItemModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        item_list = [self.get_type(info, row) for row in rows]
        return QuoteItemListType(quote_item_list=item_list, total=total)

    def insert_update(self, info: ResolveInfo, **kwargs: Any) -> Optional[Dict[str, Any]]:
        session = Config.db_session
        logger = info.context.get("logger")
        quote_uuid = kwargs.get("quote_uuid")
        quote_item_uuid = kwargs.get("quote_item_uuid")
        request_uuid = kwargs.get("request_uuid")

        try:
            if quote_item_uuid:
                # Update existing
                row = (
                    session.query(QuoteItemModel)
                    .filter(
                        QuoteItemModel.quote_uuid == quote_uuid,
                        QuoteItemModel.quote_item_uuid == quote_item_uuid,
                    )
                    .first()
                )
                if not row:
                    row = self._create_row(info, **kwargs)
                    session.add(row)
                else:
                    field_map = [
                        "provider_item_uuid",
                        "item_uuid",
                        "batch_no",
                        "request_uuid",
                        "partition_key",
                        "request_data",
                        "price_per_uom",
                        "qty",
                        "pax_breakdown",
                        "bundle_uuid",
                        "bundle_label",
                        "bundle_component_uuid",
                        "subtotal",
                        "subtotal_discount",
                        "final_subtotal",
                        "currency",
                        "subtotal_native",
                        "notes",
                        "hold_token",
                        "hold_expires_at",
                    ]
                    for field in field_map:
                        if field in kwargs:
                            val = kwargs[field]
                            setattr(
                                row,
                                field,
                                None if val == "null" else val,
                            )
                    row.updated_by = kwargs["updated_by"]
                    row.updated_at = pendulum.now("UTC")
            else:
                # Create new with server-generated UUID
                row = self._create_row(info, **kwargs)
                session.add(row)

            session.commit()
            session.refresh(row)

            # Roll up totals onto the parent quote after a successful insert.
            self._update_quote_totals(info, request_uuid, quote_uuid)

            return normalize_row(row)

        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    # --- Pricing logic (ported from DynamoDB insert_update_quote_item) ------- #

    def _create_row(self, info: ResolveInfo, **kwargs: Any) -> QuoteItemModel:
        partition_key = kwargs.get("partition_key") or info.context.get("partition_key")
        quote_uuid = kwargs.get("quote_uuid")
        request_uuid = kwargs.get("request_uuid")

        cols: Dict[str, Any] = {
            "quote_uuid": quote_uuid,
            "partition_key": partition_key,
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }

        item_uuid = kwargs.get("item_uuid")
        qty = kwargs.get("qty")
        segment_uuid = kwargs.get("segment_uuid")
        provider_item_uuid = kwargs.get("provider_item_uuid")
        batch_no = kwargs.get("batch_no")
        pax_breakdown = kwargs.get("pax_breakdown")

        if item_uuid and qty and provider_item_uuid:
            price_per_uom, subtotal = self._resolve_pricing(
                info,
                item_uuid=item_uuid,
                qty=float(qty),
                segment_uuid=segment_uuid,
                provider_item_uuid=provider_item_uuid,
                batch_no=batch_no,
                pax_breakdown=pax_breakdown,
            )
            cols["price_per_uom"] = price_per_uom
            cols["subtotal"] = subtotal
            cols["subtotal_native"] = subtotal
        else:
            # Update path or caller-provided values
            cols["price_per_uom"] = kwargs.get("price_per_uom")
            cols["subtotal"] = kwargs.get("subtotal")
            cols["subtotal_native"] = kwargs.get("subtotal_native")

        for key in [
            "provider_item_uuid",
            "item_uuid",
            "batch_no",
            "request_uuid",
            "request_data",
            "qty",
            "pax_breakdown",
            "bundle_uuid",
            "bundle_label",
            "bundle_component_uuid",
            "subtotal_discount",
            "currency",
            "notes",
            "hold_token",
            "hold_expires_at",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        # Cancellation policy snapshot (G6)
        snapshot = self._build_cancellation_snapshot(
            info, partition_key, provider_item_uuid, batch_no
        )
        if snapshot is not None:
            request_data = cols.get("request_data")
            if isinstance(request_data, dict):
                request_data["cancellation_policy_snapshot"] = snapshot
                cols["request_data"] = request_data
            else:
                cols["request_data"] = {"cancellation_policy_snapshot": snapshot}

        # Reject caller-provided cancellation_policy_snapshot (engine-owned)
        if isinstance(cols.get("request_data"), dict) and "cancellation_policy_snapshot" in cols.get(
            "request_data", {}
        ) and snapshot is None:
            raise ValueError(
                "request_data.cancellation_policy_snapshot is engine-owned"
            )

        # FX conversion from parent quote
        quote_model = self._get_parent_quote(request_uuid, quote_uuid)
        subtotal_native = float(cols.get("subtotal_native") or cols.get("subtotal") or 0)
        subtotal_display = subtotal_native

        if quote_model is not None:
            fx_rate = getattr(quote_model, "fx_rate", None)
            display_currency = getattr(quote_model, "display_currency", None)
            native_currency = cols.get("currency") or getattr(quote_model, "currency", None)
            if native_currency and "currency" not in cols:
                cols["currency"] = native_currency
            if (
                fx_rate is not None
                and display_currency
                and native_currency
                and display_currency != native_currency
            ):
                subtotal_display = subtotal_native * float(fx_rate)

        cols["subtotal"] = subtotal_display
        cols["subtotal_native"] = subtotal_native

        subtotal_discount = cols.get("subtotal_discount") or 0
        cols["final_subtotal"] = float(subtotal_display) - float(subtotal_discount or 0)

        quote_item_uuid = kwargs.get("quote_item_uuid")
        if quote_item_uuid:
            cols["quote_item_uuid"] = quote_item_uuid

        return QuoteItemModel(**cols)

    def _resolve_pricing(
        self,
        info: ResolveInfo,
        *,
        item_uuid: str,
        qty: float,
        segment_uuid: Optional[str],
        provider_item_uuid: str,
        batch_no: Optional[str] = None,
        pax_breakdown: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """Return ``(price_per_uom, subtotal)`` by resolving the pricing mode.

        Mirrors the DynamoDB ``insert_update_quote_item`` logic for ``unit``,
        ``per_pax_type``, and ``occupancy`` modes.
        """
        from ...postgresql.item import ItemModel

        session = Config.db_session
        partition_key = info.context.get("partition_key")

        item = (
            session.query(ItemModel)
            .filter(
                ItemModel.partition_key == partition_key,
                ItemModel.item_uuid == item_uuid,
            )
            .first()
        )
        pricing_mode = (getattr(item, "pricing_mode", None) or "unit") if item else "unit"

        if pricing_mode == "per_pax_type":
            if not isinstance(pax_breakdown, dict) or not pax_breakdown:
                raise ValueError("pax_breakdown is required for per_pax_type pricing")
            pax_total = 0.0
            subtotal = 0.0
            for pax_type, pax_qty in pax_breakdown.items():
                pax_qty = float(pax_qty)
                if pax_qty <= 0:
                    raise ValueError(
                        f"pax_breakdown quantities must be greater than 0, got {pax_type}={pax_qty}"
                    )
                pax_price = self._get_price_per_uom(
                    info,
                    item_uuid=item_uuid,
                    qty=pax_qty,
                    segment_uuid=segment_uuid,
                    provider_item_uuid=provider_item_uuid,
                    batch_no=batch_no,
                    pax_type=pax_type,
                )
                if pax_price is None:
                    raise ValueError(
                        f"No price tier found for item_uuid={item_uuid}, pax_type={pax_type}, "
                        f"qty={pax_qty}, segment_uuid={segment_uuid}, "
                        f"provider_item_uuid={provider_item_uuid}"
                    )
                pax_total += pax_qty
                subtotal += float(pax_price) * pax_qty
            if float(qty) != pax_total:
                raise ValueError(
                    "qty must equal the total pax_breakdown quantity for per_pax_type pricing"
                )
            price_per_uom = subtotal / pax_total
            return price_per_uom, subtotal

        if pricing_mode == "occupancy":
            if not isinstance(pax_breakdown, dict) or not pax_breakdown:
                raise ValueError("pax_breakdown is required for occupancy pricing")
            tier = self._get_occupancy_tier(
                info,
                item_uuid=item_uuid,
                qty=qty,
                segment_uuid=segment_uuid,
                provider_item_uuid=provider_item_uuid,
            )
            if tier is None or tier.price_per_uom is None:
                raise ValueError(
                    f"No occupancy base tier found for item_uuid={item_uuid}, "
                    f"qty={qty}, segment_uuid={segment_uuid}, "
                    f"provider_item_uuid={provider_item_uuid}"
                )
            base_rate = float(tier.price_per_uom)
            base_occupancy = tier.base_occupancy or {}
            extra_surcharges = tier.extra_pax_surcharges or {}
            per_uom_surcharge = 0.0
            for pt, raw_count in pax_breakdown.items():
                count = float(raw_count)
                if count < 0:
                    raise ValueError(
                        f"pax_breakdown counts must be non-negative, got {pt}={count}"
                    )
                included = float(base_occupancy.get(pt, 0))
                extras = max(0.0, count - included)
                if extras and pt not in (extra_surcharges or {}):
                    raise ValueError(
                        f"Occupancy tier missing extra_pax_surcharges entry for "
                        f"over-base pax_type={pt!r}"
                    )
                per_uom_surcharge += extras * float(extra_surcharges.get(pt, 0.0))
            price_per_uom = base_rate + per_uom_surcharge
            subtotal = price_per_uom * float(qty)
            return price_per_uom, subtotal

        # Default: unit pricing
        price_per_uom = self._get_price_per_uom(
            info,
            item_uuid=item_uuid,
            qty=qty,
            segment_uuid=segment_uuid,
            provider_item_uuid=provider_item_uuid,
            batch_no=batch_no,
        )
        if price_per_uom is None:
            raise ValueError(
                f"No price tier found for item_uuid={item_uuid}, qty={qty}, "
                f"segment_uuid={segment_uuid}, provider_item_uuid={provider_item_uuid}"
            )
        subtotal = float(price_per_uom) * float(qty)
        return price_per_uom, subtotal

    def _get_price_per_uom(
        self,
        info: ResolveInfo,
        *,
        item_uuid: str,
        qty: float,
        segment_uuid: Optional[str],
        provider_item_uuid: str,
        batch_no: Optional[str] = None,
        pax_type: Optional[str] = None,
    ) -> Optional[float]:
        """Resolve the per-UOM price from the matching ItemPriceTier.

        Mirrors ``models.dynamodb.quote_item.get_price_per_uom``:
        1. Query active tiers matching (item_uuid, provider_item_uuid,
           segment_uuid, pax_type, qty range).
        2. If the tier has a direct ``price_per_uom``, return it.
        3. Otherwise if the tier has ``margin_per_uom``, compute price from
           the matching provider item batch cost.
        """
        from ...postgresql.item_price_tier import ItemPriceTierModel
        from ...postgresql.provider_item_batch import ProviderItemBatchModel

        session = Config.db_session
        query = (
            session.query(ItemPriceTierModel)
            .filter(
                ItemPriceTierModel.item_uuid == item_uuid,
                ItemPriceTierModel.provider_item_uuid == provider_item_uuid,
                ItemPriceTierModel.status == "active",
                ItemPriceTierModel.quantity_greater_then < qty,
            )
        )
        if segment_uuid:
            query = query.filter(ItemPriceTierModel.segment_uuid == segment_uuid)
        if pax_type is not None:
            query = query.filter(ItemPriceTierModel.pax_type == pax_type)
        else:
            # legacy pax-only query: tiers without a pax_type
            query = query.filter(ItemPriceTierModel.pax_type.is_(None))

        # Tier whose qty range contains ``qty``: greater_then < qty <= less_then
        # (or less_then IS NULL for the open-ended top tier).
        query = query.filter(
            (ItemPriceTierModel.quantity_less_then.is_(None))
            | (ItemPriceTierModel.quantity_less_then >= qty)
        )
        tier = query.order_by(ItemPriceTierModel.quantity_greater_then.desc()).first()
        if tier is None:
            return None

        if tier.price_per_uom is not None:
            return float(tier.price_per_uom)

        if tier.margin_per_uom is not None:
            batches = (
                session.query(ProviderItemBatchModel)
                .filter(
                    ProviderItemBatchModel.provider_item_uuid == provider_item_uuid
                )
                .all()
            )
            prices: List[Dict[str, Any]] = []
            for batch in batches:
                if batch.slow_move_item and batch.guardrail_price_per_uom is not None:
                    price = float(batch.guardrail_price_per_uom)
                else:
                    cost = float(batch.total_cost_per_uom or 0)
                    price = cost * (1 + float(tier.margin_per_uom))
                prices.append({"batch_no": batch.batch_no, "price_per_uom": price})
            if prices:
                if batch_no:
                    for p in prices:
                        if p["batch_no"] == batch_no:
                            return p["price_per_uom"]
                return prices[0]["price_per_uom"]
        return None

    def _get_occupancy_tier(
        self,
        info: ResolveInfo,
        *,
        item_uuid: str,
        qty: float,
        segment_uuid: Optional[str],
        provider_item_uuid: str,
    ) -> Any:
        """Return the active occupancy base tier (has ``price_per_uom`` set)."""
        from ...postgresql.item_price_tier import ItemPriceTierModel

        session = Config.db_session
        query = (
            session.query(ItemPriceTierModel)
            .filter(
                ItemPriceTierModel.item_uuid == item_uuid,
                ItemPriceTierModel.provider_item_uuid == provider_item_uuid,
                ItemPriceTierModel.status == "active",
                ItemPriceTierModel.price_per_uom.isnot(None),
                ItemPriceTierModel.quantity_greater_then < qty,
            )
        )
        if segment_uuid:
            query = query.filter(ItemPriceTierModel.segment_uuid == segment_uuid)
        query = query.filter(
            (ItemPriceTierModel.quantity_less_then.is_(None))
            | (ItemPriceTierModel.quantity_less_then >= qty)
        )
        return query.order_by(ItemPriceTierModel.quantity_greater_then.desc()).first()

    def _get_parent_quote(self, request_uuid: Optional[str], quote_uuid: str) -> Any:
        """Load the parent QuoteModel for FX / currency defaults."""
        from ...postgresql.quote import QuoteModel

        session = Config.db_session
        if not request_uuid:
            return session.query(QuoteModel).filter(
                QuoteModel.quote_uuid == quote_uuid
            ).first()
        return (
            session.query(QuoteModel)
            .filter(
                QuoteModel.request_uuid == request_uuid,
                QuoteModel.quote_uuid == quote_uuid,
            )
            .first()
        )

    def _build_cancellation_snapshot(
        self,
        info: ResolveInfo,
        partition_key: str,
        provider_item_uuid: Optional[str],
        batch_no: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Snapshot the cancellation policy pinned to the batch (G6)."""
        if not batch_no or not provider_item_uuid:
            return None
        from ...postgresql.provider_item_batch import ProviderItemBatchModel
        from ...postgresql.cancellation_policy import CancellationPolicyModel

        session = Config.db_session
        batch = (
            session.query(ProviderItemBatchModel)
            .filter(
                ProviderItemBatchModel.provider_item_uuid == provider_item_uuid,
                ProviderItemBatchModel.batch_no == batch_no,
            )
            .first()
        )
        if not batch or not batch.cancellation_policy_uuid:
            return None
        policy = (
            session.query(CancellationPolicyModel)
            .filter(
                CancellationPolicyModel.partition_key == partition_key,
                CancellationPolicyModel.policy_uuid == batch.cancellation_policy_uuid,
            )
            .first()
        )
        if not policy:
            return None
        return {
            "policy_uuid": str(policy.policy_uuid),
            "label": policy.label,
            "description": policy.description,
            "tiers": policy.tiers,
            "notes_template_uuid": str(policy.notes_template_uuid)
            if policy.notes_template_uuid
            else None,
            "snapshotted_at": pendulum.now("UTC").to_iso8601_string(),
        }

    def _update_quote_totals(
        self, info: ResolveInfo, request_uuid: Optional[str], quote_uuid: str
    ) -> None:
        """Recalculate parent quote totals from all quote items."""
        from ...postgresql.quote import QuoteModel

        session = Config.db_session
        quote = self._get_parent_quote(request_uuid, quote_uuid)
        if quote is None:
            return
        items = (
            session.query(QuoteItemModel)
            .filter(QuoteItemModel.quote_uuid == quote_uuid)
            .all()
        )
        total_quote_amount = sum(float(i.subtotal or 0) for i in items)
        total_quote_discount = sum(
            float(i.subtotal_discount or 0) for i in items
        )
        items_final_total = sum(float(i.final_subtotal or 0) for i in items)
        shipping_amount = float(quote.shipping_amount or 0)
        quote.total_quote_amount = total_quote_amount
        quote.total_quote_discount = total_quote_discount if total_quote_discount > 0 else 0
        quote.final_total_quote_amount = items_final_total + shipping_amount
        quote.updated_at = pendulum.now("UTC")
        session.commit()

    def delete(self, info: ResolveInfo, **kwargs: Any) -> bool:
        session = Config.db_session
        logger = info.context.get("logger")
        quote_uuid = kwargs.get("quote_uuid")
        quote_item_uuid = kwargs.get("quote_item_uuid")

        try:
            # Check for dependent installments
            from ...postgresql.installment import InstallmentModel

            dep_count = (
                session.query(InstallmentModel)
                .filter(
                    InstallmentModel.quote_uuid == quote_uuid,
                )
                .count()
            )
            if dep_count > 0:
                return False

            row = (
                session.query(QuoteItemModel)
                .filter(
                    QuoteItemModel.quote_uuid == quote_uuid,
                    QuoteItemModel.quote_item_uuid == quote_item_uuid,
                )
                .first()
            )
            if not row:
                return True  # Already deleted

            session.delete(row)
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            if logger:
                logger.error(traceback.format_exc())
            raise e

    def get_type(self, info: ResolveInfo, row: Any) -> QuoteItemType:
        """Convert a SQLAlchemy row to QuoteItemType."""
        data = normalize_row(row)
        if data is None:
            return None
        return QuoteItemType(**normalize_to_json(data))

    def resolve_single(self, info: ResolveInfo, **kwargs: Any) -> Optional[QuoteItemType]:
        """Resolve a single quote item by quote_uuid and quote_item_uuid."""
        quote_uuid = kwargs.get("quote_uuid")
        quote_item_uuid = kwargs.get("quote_item_uuid")
        if not quote_uuid or not quote_item_uuid:
            return None

        count = self.count(
            quote_uuid=quote_uuid, quote_item_uuid=quote_item_uuid
        )
        if count == 0:
            return None

        row = (
            Config.db_session.query(QuoteItemModel)
            .filter(
                QuoteItemModel.quote_uuid == quote_uuid,
                QuoteItemModel.quote_item_uuid == quote_item_uuid,
            )
            .first()
        )
        return self.get_type(info, row) if row else None


__all__ = ["QuoteItemPGRepository"]