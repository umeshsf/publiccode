CREATE SCHEMA IF NOT EXISTS retail;

SET search_path TO retail;
-- Drop tables in reverse order to handle foreign key dependencies for clean re-creation
DROP TABLE IF EXISTS retail.reviews CASCADE;
DROP TABLE IF EXISTS retail.productcategories CASCADE;
DROP TABLE IF EXISTS retail.orderitems CASCADE;
DROP TABLE IF EXISTS retail.orders CASCADE;
DROP TABLE IF EXISTS retail.products CASCADE;
DROP TABLE IF EXISTS retail.categories CASCADE;
DROP TABLE IF EXISTS retail.customers CASCADE;

-- Create Customers Table
CREATE TABLE retail.customers (
    CustomerId SERIAL PRIMARY KEY, -- SERIAL for auto-incrementing integer primary key
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    Email VARCHAR(100) NOT NULL UNIQUE, -- Added UNIQUE constraint as emails are typically unique
    Phone VARCHAR(20),
    Address VARCHAR(255),
    City VARCHAR(100),
    State VARCHAR(50),
    ZipCode VARCHAR(10),
    DateCreated TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(), -- NOW() for current timestamp
    LastUpdated TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
-- Set REPLICA IDENTITY to DEFAULT for Customers table
ALTER TABLE retail.customers REPLICA IDENTITY DEFAULT;

-- Create Products Table
CREATE TABLE retail.products (
    ProductId SERIAL PRIMARY KEY, -- SERIAL for auto-incrementing integer primary key
    ProductName VARCHAR(100) NOT NULL,
    Description TEXT, -- NVARCHAR(MAX) converted to TEXT
    Price NUMERIC(10, 2) NOT NULL, -- DECIMAL is an alias for NUMERIC in PostgreSQL
    StockQuantity INT NOT NULL,
    DateAdded TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    LastUpdated TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
-- Set REPLICA IDENTITY to DEFAULT for Products table
ALTER TABLE retail.products REPLICA IDENTITY DEFAULT;

-- Create Categories Table
CREATE TABLE retail.categories (
    CategoryId SERIAL PRIMARY KEY, -- SERIAL for auto-incrementing integer primary key
    CategoryName VARCHAR(100) NOT NULL,
    Description TEXT -- NVARCHAR(MAX) converted to TEXT
);
-- Set REPLICA IDENTITY to DEFAULT for Categories table
ALTER TABLE retail.categories REPLICA IDENTITY DEFAULT;


-- Create Orders Table
CREATE TABLE retail.orders (
    OrderId SERIAL PRIMARY KEY, -- SERIAL for auto-incrementing integer primary key
    CustomerId INT NOT NULL,
    OrderDate TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    TotalAmount NUMERIC(10, 2) NOT NULL,
    OrderStatus VARCHAR(50) NOT NULL,
    ShippingAddress VARCHAR(255),
    ShippingCity VARCHAR(100),
    ShippingState VARCHAR(50),
    ShippingZipCode VARCHAR(10),
    FOREIGN KEY (CustomerId) REFERENCES retail.customers(CustomerId)
);
-- Set REPLICA IDENTITY to DEFAULT for Orders table
ALTER TABLE retail.orders REPLICA IDENTITY DEFAULT;

-- Create OrderItems Table
CREATE TABLE retail.orderitems (
    OrderItemId SERIAL PRIMARY KEY, -- SERIAL for auto-incrementing integer primary key
    OrderId INT NOT NULL,
    ProductId INT NOT NULL,
    Quantity INT NOT NULL,
    UnitPrice NUMERIC(10, 2) NOT NULL,
    FOREIGN KEY (OrderId) REFERENCES retail.orders(OrderId),
    FOREIGN KEY (ProductId) REFERENCES retail.products(ProductId)
);
-- Set REPLICA IDENTITY to DEFAULT for OrderItems table
ALTER TABLE retail.orderitems REPLICA IDENTITY DEFAULT;

-- Create ProductCategories Junction Table
-- This table requires a composite primary key to ensure unique product-category pairings.
CREATE TABLE retail.productcategories (
    ProductId INT NOT NULL,
    CategoryId INT NOT NULL,
    PRIMARY KEY (ProductId, CategoryId), -- Composite Primary Key
    FOREIGN KEY (ProductId) REFERENCES retail.products(ProductId),
    FOREIGN KEY (CategoryId) REFERENCES retail.categories(CategoryId)
);
-- Set REPLICA IDENTITY to DEFAULT for ProductCategories table
ALTER TABLE retail.productcategories REPLICA IDENTITY DEFAULT;

-- Create Reviews Table
CREATE TABLE retail.reviews (
    ReviewId SERIAL PRIMARY KEY, -- SERIAL for auto-incrementing integer primary key
    ProductId INT NOT NULL,
    CustomerId INT NOT NULL,
    Rating INT NOT NULL,
    Comment TEXT, -- NVARCHAR(MAX) converted to TEXT
    ReviewDate TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (ProductId) REFERENCES retail.products(ProductId),
    FOREIGN KEY (CustomerId) REFERENCES retail.customers(CustomerId)
);
-- Set REPLICA IDENTITY to DEFAULT for Reviews table
ALTER TABLE retail.reviews REPLICA IDENTITY DEFAULT;

-- Optional: Add triggers to automatically update LastUpdated columns
-- for Customers
CREATE OR REPLACE FUNCTION update_customers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.LastUpdated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_customers_updated_at
BEFORE UPDATE ON retail.customers
FOR EACH ROW
EXECUTE FUNCTION update_customers_updated_at();

-- for Products
CREATE OR REPLACE FUNCTION update_products_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.LastUpdated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_products_updated_at
BEFORE UPDATE ON retail.products
FOR EACH ROW
EXECUTE FUNCTION update_products_updated_at();


-- Sample Data Insertion (matching the image)
-- TRUNCATE statements for re-running the script
TRUNCATE TABLE retail.reviews RESTART IDENTITY CASCADE;
TRUNCATE TABLE retail.productcategories RESTART IDENTITY CASCADE;
TRUNCATE TABLE retail.orderitems RESTART IDENTITY CASCADE;
TRUNCATE TABLE retail.orders RESTART IDENTITY CASCADE;
TRUNCATE TABLE retail.products RESTART IDENTITY CASCADE;
TRUNCATE TABLE retail.categories RESTART IDENTITY CASCADE;
TRUNCATE TABLE retail.customers RESTART IDENTITY CASCADE;


-- Insert Sample Data into Customers
INSERT INTO retail.customers (FirstName, LastName, Email, Phone, Address, City, State, ZipCode) VALUES
('Alice', 'Smith', 'alice.smith@example.com', '555-111-2222', '123 Main St', 'Anytown', 'CA', '90210'),
('Bob', 'Johnson', 'bob.johnson@example.com', '555-333-4444', '456 Oak Ave', 'Otherville', 'NY', '10001');

-- Insert Sample Data into Products
INSERT INTO retail.products (ProductName, Description, Price, StockQuantity) VALUES
('Laptop Pro', 'High-performance laptop', 1200.00, 50),
('Wireless Mouse', 'Ergonomic wireless mouse', 25.50, 200),
('Mechanical Keyboard', 'RGB Mechanical keyboard', 75.00, 100);

-- Insert Sample Data into Categories
INSERT INTO retail.categories (CategoryName, Description) VALUES
('Electronics', 'Devices and gadgets'),
('Peripherals', 'Computer accessories');

-- Insert Sample Data into Orders
-- Get CustomerId from previous inserts (assuming 1 and 2 for Alice and Bob)
INSERT INTO retail.orders (CustomerId, TotalAmount, OrderStatus, ShippingAddress, ShippingCity, ShippingState, ShippingZipCode) VALUES
(1, 1225.50, 'Processing', '123 Main St', 'Anytown', 'CA', '90210'),
(2, 75.00, 'Shipped', '456 Oak Ave', 'Otherville', 'NY', '10001');

-- Insert Sample Data into OrderItems
-- Assuming OrderId 1 and 2, ProductId 1, 2, 3 from previous inserts
INSERT INTO retail.orderitems (OrderId, ProductId, Quantity, UnitPrice) VALUES
(1, 1, 1, 1200.00), -- Laptop Pro for Order 1
(1, 2, 1, 25.50),  -- Wireless Mouse for Order 1
(2, 3, 1, 75.00);   -- Mechanical Keyboard for Order 2

-- Insert Sample Data into ProductCategories
INSERT INTO retail.productcategories (ProductId, CategoryId) VALUES
(1, 1), -- Laptop Pro is Electronics
(2, 2), -- Wireless Mouse is Peripherals
(3, 2); -- Mechanical Keyboard is Peripherals

-- Insert Sample Data into Reviews
INSERT INTO retail.reviews (ProductId, CustomerId, Rating, Comment) VALUES
(1, 1, 5, 'Great laptop, very fast!'),
(3, 2, 4, 'Solid keyboard, good feel.');

WITH all_tables AS
(
SELECT 'categories' AS TABLE_NAME, COUNT (*) AS ROW_COUNT FROM retail."categories"  
union ALL
SELECT 'customers' AS TABLE_NAME, COUNT (*) AS ROW_COUNT FROM retail."customers"  
union ALL
SELECT 'orderitems' AS TABLE_NAME, COUNT (*) AS ROW_COUNT FROM retail."orderitems"    
union ALL
SELECT 'orders' AS TABLE_NAME, COUNT (*) AS ROW_COUNT FROM retail."orders"  
union ALL
SELECT 'productcategories' AS TABLE_NAME, COUNT (*) AS ROW_COUNT FROM retail."productcategories"  
union ALL
SELECT 'products' AS TABLE_NAME, COUNT (*) AS ROW_COUNT FROM retail."products"  
union ALL
SELECT 'reviews' AS TABLE_NAME, COUNT (*) AS ROW_COUNT FROM retail."reviews"        
)
select * from all_tables
union all
select 'all', sum(row_Count) from all_tables;


CREATE PUBLICATION retail_openflow_sync
    FOR TABLE retail."orders", retail."products", retail."customers"
    WITH (publish = 'insert, update, delete, truncate', publish_via_partition_root = true);
