# ShipStation API V2 - Complete Endpoint Reference

Generated from the official spec: `https://docs.shipstation.com/_spec/apis/@shipstation-v2/openapi.yaml`

- **Base URL:** `https://api.shipstation.com` (paths below already include the `/v2` prefix)
- **Auth header:** `API-Key: <your key>`
- **142 operations across 30 path roots**

Regenerate this file if it looks stale - see SKILL.md 'Verifying against the live spec'.

---

## `/v2/account`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/account/settings` | `list_account_settings` | - |
| GET | `/v2/account/settings/images` | `list_account_images` | - |
| POST | `/v2/account/settings/images` | `create_account_image` | - |
| DELETE | `/v2/account/settings/images/{label_image_id}` | `delete_account_image_by_id` | - |
| GET | `/v2/account/settings/images/{label_image_id}` | `get_account_settings_images_by_id` | - |
| PUT | `/v2/account/settings/images/{label_image_id}` | `update_account_settings_images_by_id` | - |

## `/v2/addresses`

| Method | Path | Operation | Query params |
|---|---|---|---|
| POST | `/v2/addresses/validate` | `validate_address` | - |

## `/v2/batches`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/batches` | `list_batches` | `batch_status`, `page`, `page_size`, `sort_dir`, `batch_number`, `sort_by` |
| POST | `/v2/batches` | `create_batch` | - |
| DELETE | `/v2/batches/{batch_id}` | `delete_batch` | - |
| GET | `/v2/batches/{batch_id}` | `get_batch_by_id` | - |
| PUT | `/v2/batches/{batch_id}` | `update_batch` | - |
| POST | `/v2/batches/{batch_id}/add` | `add_to_batch` | - |
| GET | `/v2/batches/{batch_id}/errors` | `list_batch_errors` | `page`, `pagesize` |
| POST | `/v2/batches/{batch_id}/process/labels` | `process_batch` | - |
| POST | `/v2/batches/{batch_id}/remove` | `remove_from_batch` | - |
| GET | `/v2/batches/external_batch_id/{external_batch_id}` | `get_batch_by_external_id` | - |

## `/v2/carriers`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/carriers` | `list_carriers` | `page`, `page_size`, `include_extended_details` |
| DELETE | `/v2/carriers/{carrier_id}` | `disconnect_carrier_by_id` | - |
| GET | `/v2/carriers/{carrier_id}` | `get_carrier_by_id` | - |
| PUT | `/v2/carriers/{carrier_id}/add_funds` | `add_funds_to_carrier` | - |
| GET | `/v2/carriers/{carrier_id}/options` | `get_carrier_options` | - |
| GET | `/v2/carriers/{carrier_id}/packages` | `list_carrier_package_types` | - |
| GET | `/v2/carriers/{carrier_id}/services` | `list_carrier_services` | - |

## `/v2/connections`

| Method | Path | Operation | Query params |
|---|---|---|---|
| POST | `/v2/connections/carriers/{carrier_name}` | `connect_carrier` | - |
| DELETE | `/v2/connections/carriers/{carrier_name}/{carrier_id}` | `disconnect_carrier` | - |
| GET | `/v2/connections/carriers/{carrier_name}/{carrier_id}/settings` | `get_carrier_settings` | - |
| PUT | `/v2/connections/carriers/{carrier_name}/{carrier_id}/settings` | `update_carrier_settings` | - |

## `/v2/documents`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/documents/{document_id}/download` | `download_document` | - |
| POST | `/v2/documents/combined_labels` | `create_combined_label_document` | - |

## `/v2/downloads`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/downloads/{dir}/{subdir}/{filename}` | `download_file` | `download`, `rotation` |

## `/v2/environment`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/environment/webhooks` | `list_webhooks` | - |
| POST | `/v2/environment/webhooks` | `create_webhook` | - |
| DELETE | `/v2/environment/webhooks/{webhook_id}` | `delete_webhook` | - |
| GET | `/v2/environment/webhooks/{webhook_id}` | `get_webhook_by_id` | - |
| PUT | `/v2/environment/webhooks/{webhook_id}` | `update_webhook` | - |

## `/v2/fulfillments`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/fulfillments` | `list_fulfillments` | `ship_to_name`, `ship_to_country_code`, `shipment_number`, `shipment_id`, `fulfillment_id`, `batch_id`, `order_source_id`, `fulfillment_provider_code`, `tracking_number`, `ship_date_start`, `ship_date_end`, `create_date_start`, `create_date_end`, `page`, `page_size`, `sort_dir`, `sort_by` |
| POST | `/v2/fulfillments` | `create_fulfillments` | - |

## `/v2/inventory`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/inventory` | `getInventoryLevels` | `sku`, `inventory_warehouse_id`, `inventory_location_id`, `group_by`, `page_size` |
| POST | `/v2/inventory` | `updateSKUStockLevels` | - |

## `/v2/inventory_locations`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/inventory_locations` | `listInventoryLocations` | `page_size` |
| POST | `/v2/inventory_locations` | `createInventoryLocation` | - |
| DELETE | `/v2/inventory_locations/{inventory_location_id}` | `deleteInventoryLocationById` | `remove_inventory` |
| GET | `/v2/inventory_locations/{inventory_location_id}` | `getInventoryLocationById` | - |
| PUT | `/v2/inventory_locations/{inventory_location_id}` | `updateInventoryLocation` | - |

## `/v2/inventory_warehouses`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/inventory_warehouses` | `getInventoryWarehouses` | `page_size` |
| POST | `/v2/inventory_warehouses` | `addNewInventoryWarehouse` | - |
| DELETE | `/v2/inventory_warehouses/{inventory_warehouse_id}` | `deleteInventoryWarehouse` | `remove_inventory` |
| GET | `/v2/inventory_warehouses/{inventory_warehouse_id}` | `getInventoryWarehouseById` | - |
| PUT | `/v2/inventory_warehouses/{inventory_warehouse_id}` | `updateInventoryWarehouse` | - |

## `/v2/labels`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/labels` | `list_labels` | `label_status`, `service_code`, `carrier_id`, `tracking_number`, `batch_id`, `rate_id`, `shipment_id`, `external_shipment_id`, `warehouse_id`, `created_at_start`, `created_at_end`, `refund_status`, `page`, `page_size`, `sort_dir`, `sort_by` |
| POST | `/v2/labels` | `create_label` | - |
| GET | `/v2/labels/{label_id}` | `get_label_by_id` | `label_download_type` |
| POST | `/v2/labels/{label_id}/cancel_refund` | `cancel_label_refund` | - |
| GET | `/v2/labels/{label_id}/documents` | `list_label_documents` | - |
| POST | `/v2/labels/{label_id}/documents` | `register_label_document` | - |
| DELETE | `/v2/labels/{label_id}/documents/{document_id}` | `delete_label_document` | - |
| POST | `/v2/labels/{label_id}/documents/send` | `send_label_documents` | - |
| POST | `/v2/labels/{label_id}/return` | `create_return_label` | - |
| GET | `/v2/labels/{label_id}/track` | `get_tracking_log_from_label` | - |
| PUT | `/v2/labels/{label_id}/void` | `void_label` | - |
| GET | `/v2/labels/external_shipment_id/{external_shipment_id}` | `get_label_by_external_shipment_id` | `label_download_type` |
| POST | `/v2/labels/rate_shopper_id/{rate_shopper_id}` | `create_label_from_rate_shopper` | - |
| POST | `/v2/labels/rates/{rate_id}` | `create_label_from_rate` | - |
| POST | `/v2/labels/shipment/{shipment_id}` | `create_label_from_shipment` | - |
| POST | `/v2/labels/shipping_rules/{shipping_rule_id}` | `create_label_from_shipping_rule` | - |

## `/v2/mailing`

| Method | Path | Operation | Query params |
|---|---|---|---|
| POST | `/v2/mailing/envelopes` | `create_envelope` | - |
| POST | `/v2/mailing/mail_labels` | `create_mailing_labels` | - |
| POST | `/v2/mailing/netstamps` | `create_netstamps` | - |

## `/v2/manifests`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/manifests` | `list_manifests` | `warehouse_id`, `ship_date_start`, `ship_date_end`, `created_at_start`, `created_at_end`, `carrier_id`, `page`, `page_size`, `label_ids` |
| POST | `/v2/manifests` | `create_manifest` | - |
| GET | `/v2/manifests/{manifest_id}` | `get_manifest_by_id` | - |
| GET | `/v2/manifests/requests/{manifest_request_id}` | `get_manifest_request_by_id` | - |

## `/v2/packages`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/packages` | `list_package_types` | - |
| POST | `/v2/packages` | `create_package_type` | - |
| DELETE | `/v2/packages/{package_id}` | `delete_package_typ` | - |
| GET | `/v2/packages/{package_id}` | `get_package_type_by_id` | - |
| PUT | `/v2/packages/{package_id}` | `update_package_type` | - |

## `/v2/pickups`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/pickups` | `list_scheduled_pickups` | `carrier_id`, `warehouse_id`, `created_at_start`, `created_at_end`, `page`, `page_size` |
| POST | `/v2/pickups` | `schedule_pickup` | - |
| DELETE | `/v2/pickups/{pickup_id}` | `delete_scheduled_pickup` | - |
| GET | `/v2/pickups/{pickup_id}` | `get_pickup_by_id` | - |

## `/v2/products`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/products` | `listProducts` | `sku`, `name`, `active`, `page_size`, `page` |

## `/v2/purchase_orders`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/purchase_orders` | `list_purchase_orders` | `order_number`, `status`, `warehouse_id`, `reference_number`, `create_date_start`, `page_size` |
| POST | `/v2/purchase_orders` | `create_purchase_order` | - |
| GET | `/v2/purchase_orders/{purchase_order_id}` | `get_purchase_order` | - |
| PUT | `/v2/purchase_orders/{purchase_order_id}` | `update_purchase_order` | - |
| GET | `/v2/purchase_orders/{purchase_order_id}/documents/order_summary` | `get_purchase_order_summary_pdf` | - |
| GET | `/v2/purchase_orders/{purchase_order_id}/documents/received_summary` | `get_purchase_order_received_summary_pdf` | - |
| POST | `/v2/purchase_orders/{purchase_order_id}/receives` | `receives_purchase_order_products` | - |
| POST | `/v2/purchase_orders/{purchase_order_id}/shipping_details` | `update_purchase_order_shipping_details` | - |
| POST | `/v2/purchase_orders/{purchase_order_id}/status` | `update_purchase_order_status` | - |

## `/v2/rate_shoppers`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/rate_shoppers` | `list_rate_shoppers` | `type`, `sort_by`, `sort_dir` |
| GET | `/v2/rate_shoppers/{rate_shopper_id}` | `get_rate_shopper_by_id` | - |

## `/v2/rates`

| Method | Path | Operation | Query params |
|---|---|---|---|
| POST | `/v2/rates` | `calculate_rates` | - |
| GET | `/v2/rates/{rate_id}` | `get_rate_by_id` | - |
| POST | `/v2/rates/bulk` | `compare_bulk_rates` | - |
| POST | `/v2/rates/estimate` | `estimate_rates` | - |

## `/v2/service_points`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/service_points/{carrier_code}/{country_code}/{service_point_id}` | `service_points_get_by_id` | - |
| POST | `/v2/service_points/list` | `service_points_list` | - |

## `/v2/shipments`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/shipments` | `list_shipments` | `shipment_status`, `batch_id`, `pickup_id`, `created_at_start`, `created_at_end`, `modified_at_start`, `modified_at_end`, `page`, `page_size`, `sales_order_id`, `sort_dir`, `shipment_number`, `ship_to_name`, `item_keyword`, `payment_date_start`, `payment_date_end`, `store_id`, `external_shipment_id`, `sort_by` |
| POST | `/v2/shipments` | `create_shipments` | - |
| GET | `/v2/shipments/{shipment_id}` | `get_shipment_by_id` | - |
| PUT | `/v2/shipments/{shipment_id}` | `update_shipment` | - |
| PUT | `/v2/shipments/{shipment_id}/cancel` | `cancel_shipments` | - |
| GET | `/v2/shipments/{shipment_id}/documents` | `list_shipment_documents` | - |
| POST | `/v2/shipments/{shipment_id}/documents` | `register_shipment_document` | - |
| DELETE | `/v2/shipments/{shipment_id}/documents/{document_id}` | `delete_shipment_document` | - |
| POST | `/v2/shipments/{shipment_id}/internal_notes` | `update_shipment_internal_notes` | - |
| GET | `/v2/shipments/{shipment_id}/labels` | `list_shipment_label_documents` | - |
| GET | `/v2/shipments/{shipment_id}/rates` | `list_shipment_rates` | `created_at_start` |
| GET | `/v2/shipments/{shipment_id}/tags` | `shipments_list_tags` | - |
| DELETE | `/v2/shipments/{shipment_id}/tags/{tag_name}` | `untag_shipment` | - |
| POST | `/v2/shipments/{shipment_id}/tags/{tag_name}` | `tag_shipment` | - |
| GET | `/v2/shipments/external_shipment_id/{external_shipment_id}` | `get_shipment_by_external_id` | - |
| POST | `/v2/shipments/user` | `assign_user_to_shipments` | - |

## `/v2/suppliers`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/suppliers` | `list_suppliers` | `supplier_name`, `page_size` |
| POST | `/v2/suppliers` | `create_supplier` | - |
| GET | `/v2/suppliers/{supplier_id}` | `get_supplier` | - |
| PUT | `/v2/suppliers/{supplier_id}` | `update_supplier` | - |

## `/v2/tags`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/tags` | `list_tags` | - |
| POST | `/v2/tags` | `create_tag` | - |
| DELETE | `/v2/tags/{tag_name}` | `delete_tag` | - |
| POST | `/v2/tags/{tag_name}` | `create_tag_by_name` | - |
| PUT | `/v2/tags/{tag_name}/{new_tag_name}` | `rename_tag` | - |

## `/v2/tokens`

| Method | Path | Operation | Query params |
|---|---|---|---|
| POST | `/v2/tokens/ephemeral` | `tokens_get_ephemeral_token` | `redirect` |

## `/v2/totes`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/totes` | `listTotes` | `inventory_warehouse_id` |
| POST | `/v2/totes` | `createTotesBatch` | - |
| DELETE | `/v2/totes/{tote_id}` | `deleteTote` | - |
| GET | `/v2/totes/{tote_id}` | `getToteById` | - |
| PUT | `/v2/totes/{tote_id}` | `updateTote` | - |
| GET | `/v2/totes/quantities` | `getToteQuantities` | - |

## `/v2/tracking`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/tracking` | `get_tracking_log` | `carrier_code`, `tracking_number`, `carrier_id` |
| POST | `/v2/tracking/start` | `start_tracking` | `carrier_code`, `tracking_number`, `carrier_id` |
| POST | `/v2/tracking/stop` | `stop_tracking` | `carrier_code`, `tracking_number` |

## `/v2/users`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/users` | `listUsers` | `status`, `page_size`, `page` |

## `/v2/warehouses`

| Method | Path | Operation | Query params |
|---|---|---|---|
| GET | `/v2/warehouses` | `list_warehouses` | - |
| POST | `/v2/warehouses` | `create_warehouse` | - |
| DELETE | `/v2/warehouses/{warehouse_id}` | `delete_warehouse` | - |
| GET | `/v2/warehouses/{warehouse_id}` | `get_warehouse_by_id` | - |
| PUT | `/v2/warehouses/{warehouse_id}` | `update_warehouse` | - |
| PUT | `/v2/warehouses/{warehouse_id}/settings` | `update_warehouse_settings` | - |

