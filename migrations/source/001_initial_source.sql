BEGIN;

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    amount BIGINT NOT NULL CHECK (amount >= 0),
    campaign_id TEXT NULL
);

CREATE TABLE order_items (
    item_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

COMMIT;
