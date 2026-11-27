\set ON_ERROR_STOP on

ALTER TABLE commerce.transaction_events
    DROP CONSTRAINT IF EXISTS transaction_events_event_type_check;
ALTER TABLE commerce.transaction_events
    ADD CONSTRAINT transaction_events_event_type_check CHECK (
        event_type IN (
            'CUSTOMER_CREATED', 'ORDER_CREATED', 'PAYMENT_UPDATED',
            'SHIPMENT_UPDATED', 'PRODUCT_UPDATED', 'CONTROLLED_DELETE',
            'PROBE_WRITE'
        )
    );
