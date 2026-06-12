# Product Requirements Document (PRD)
## Digital Storefront & Store Management System for Social Media Sellers

---

### 1. Problem Statement
Businesses in Ethiopia increasingly leverage social media platforms like **Telegram** and **Instagram** to market and sell their products. However, the majority of these micro-enterprises operate without a structured e-commerce backend or management system. 

This status quo introduces distinct operational pain points:
* **For Sellers:** Inefficient and chaotic order management, restricted sales scalability, and an inability to track or analyze historical customer interactions.
* **For Buyers:** Fragmented and frustrating purchasing journeys characterized by repetitive back-and-forth messaging, opaque product information, uncertain stock availability, cumbersome order flows, and diminished trust regarding payment and fulfillment.

**Solution:** This project delivers a locally optimized digital storefront and intuitive store management system designed to streamline decentralized online transactions, elevate the customer experience, and empower merchants to systematically organize and scale their digital sales.

---

### 2. Success Metrics
To evaluate the impact and adoption of the platform, the following key performance indicators (KPIs) have been established:
* **Inquiry Reduction:** Achieve a **50% reduction** in manual, repetitive customer inquiries after platform adoption.
* **Transaction Speed:** Lower the average order completion time from an estimated manual baseline of 30 minutes down to **under 8 minutes**.
* **Order Accuracy:** Maintain a **0% missed order rate** driven entirely by automated background order capture.
* **Customer Satisfaction:** Realize an average post-purchase customer satisfaction score of **≥ 4/5**, actively evaluated via an automated post-purchase SMS survey: *"How would you rate your ordering experience? (1-5)"*.

---

### 3. User Persona Stories

#### A. The Merchant / Seller
* **Persona Profile:** *Fanuel*, runs an independent clothing shop processing roughly 20 to 30 orders per month.
* **User Story 1 (Authentication):** As a seller, I want to log into my dashboard using my phone number combined with a One-Time Password (OTP) so that my storefront metrics are secured without the friction of remembering or resetting passwords.
* **User Story 2 (Catalog Management):** As a seller, I want to seamlessly build out product listings complete with descriptive photos, localized pricing, and customizable sizing/quantity matrices, preventing buyers from continuously messaging me for base details.
* **User Story 3 (Order Tracking):** As a seller, I need to visualize all incoming orders in a single, centralized pane sorted chronologically (oldest first) so that no transaction is ever dropped or delayed.
* **User Story 4 (Fulfillment Status):** As a seller, I want to progressively advance order statuses from *Pending* to *Confirmed* to *Completed* so that buyers remain informed, effectively mitigating disputes or refund complaints.

#### B. The Consumer / Buyer
* **Persona Profile:** *Dawit*, 24 years old, frequently purchases streetwear and hoodies online.
* **User Story 5 (Self-Service Browsing):** As a buyer, I want to browse an organized product grid with transparent pricing, high-resolution imagery, and live stock statuses so that I can make immediate purchasing decisions without exchanging a dozen messages.
* **User Story 6 (Purchase Proof):** As a buyer, I want an instantaneous order confirmation containing a unique Order ID and the merchant's direct contact details, providing explicit proof of purchase and a clear roadmap for fulfillment.

---

### 4. Functional Requirements (FR)

#### 4.1 Product Catalog & Listings
* **FR1 (Core Schema):** The system must allow sellers to generate products containing a Name, Description, Price, multiple associated photos, and an `InStock` boolean flag.
* **FR2 (Image Assets):** Sellers must have the option to upload multiple photo assets per product, tagging each asset with a structural classification: `main`, `thumbnail`, or `gallery`.
* **FR3 (Product Attributes):** The system must optionally capture product attributes, specifically:
    * *Sizes:* `S`, `M`, `L`, `XL`
    * *Colors:* `Red`, `Blue`, `Black`, `White`
* **FR4 (Visibility Logic):** Products explicitly flagged as *Sold Out* (`InStock = false`) must be automatically hidden from public-facing buyer storefronts, while remaining fully visible and editable within the private seller dashboard for restocking.
* **FR5 (Exploit Prevention):** The system must rigorously reject any checkout attempts on *Sold Out* items, ensuring that even if a buyer bypasses browsing via a direct product link, an order cannot be processed.
* **FR6 (Catalog Updating):** Sellers must be able to update all primary product attributes dynamically (name, description, price, stock flag) and seamlessly replace or re-order associated images.

#### 4.2 Buyer Browsing & Checkout Engine
* **FR7 (Responsive Grid Layout):** Buyers must be presented with a responsive grid layout displaying product thumbnail cards (photo, name, price, stock indicator) optimized seamlessly across mobile and desktop Viewports.
* **FR8 (Detailed View):** Clicking a product card must open a detailed product layout showcasing the complete photo gallery, full description, price points, attribute configurations, and a prominent *Buy Now* Call-to-Action.
* **FR9 (Input Constraints):** Prior to initiating checkout, the buyer must select an explicit quantity (bounded between 1 and 10 units) and configure necessary product variants (size and color).
* **FR10 (Minimalist Checkout):** The checkout interface must collect exactly three customer input fields to minimize friction: *Full Name*, *Phone Number*, and *Delivery Address*.
* **FR11 (Input Validation):** The system must strictly halt processing if the provided phone number is structurally invalid. Valid numbers must be exactly **10 digits** long and commence with either **09** or **07**.

#### 4.3 Order Ingestion, Confirmation & Lifecycle Tracking
* **FR12 (Structured Order ID):** Upon successful checkout submission, the engine must auto-generate a unique, standardized Order ID using the following strict nomenclature: 
    `ET-[store_prefix]-[YYYYMMDD]-[0001]` *(e.g., ET-HOODIE-20250521-0001)*.
* **FR13 (Store Branding Prefix):** Merchants will define an explicit alphanumeric Store Name during initial onboarding, which the system will automatically parse and slugify to form the `[store_prefix]` block.
* **FR14 (Success Viewport):** Buyers must be immediately redirected to a clear confirmation view showing their unique Order ID, the aggregated total cost, and the merchant's localized phone number or Telegram link.
* **FR15 (Omnichannel Notifications):** The system must automatically dispatch a receipt copy via SMS or Telegram (respecting the buyer's explicitly toggled system preference) mirroring the Order ID and transaction summary.
* **FR16 (Auditable Ledgers):** Every transaction must be committed to the database alongside an immutable creation timestamp, buyer data payloads, item metadata, and an explicit state flag.
* **FR17 (State Machine Workflow):** The order state machine must flow sequentially: `pending` (default state upon ingestion) $
ightarrow$ `shipped` $
ightarrow$ `completed` (successfully delivered). Symmetrically, a merchant can flag an active order as `cancelled`.
* **FR18 (Terminal State Integrity):** The system must enforce terminal state locks. Once an order settles into `completed` or `cancelled`, the system must block any subsequent programmatic modifications to its status.

#### 4.4 Comprehensive Seller Dashboard
* **FR19 (Passwordless Authentication):** Access control to the seller workspace is strictly authenticated via mobile phone numbers validated against a temporary One-Time Password (OTP) dispatched over SMS or Telegram.
* **FR20 (Tabular Workspace View):** The primary view must output a clean, filterable data table containing columns for: *Order ID*, *Buyer Name*, *Target Product*, *Quantity*, *Total Amount (Birr)*, *Current Status*, and *Created At Timestamp*.
* **FR21 (Chronological Sorting):** Incoming data matrices must automatically sort by oldest `pending` rows first, maximizing fulfillment visibility.
* **FR22 (Granular Inspector & Mutations):** Clicking a specific order row must launch an analytical view displaying full delivery instructions, phone contact details, and precise attribute maps, alongside an inline dropdown to mutate order status.
* **FR23 (Instant Dispatch Triggers):** Sellers must receive immediate push-style alerts (via Telegram webhook or SMS) the second a buyer completes a transaction, explicitly stating the incoming Order ID and Buyer Name.

---

### 5. Non-Functional Requirements (NFR)

#### 5.1 Performance & Latency Targets
* **Storefront Ingestion:** Public-facing product catalog grids must achieve a Document Object Model (DOM) interactive loading threshold of **under 3 seconds** when evaluated over standard local **3G connections**.
* **Transactional Submissions:** The complete transactional pipeline—from clicking checkout to displaying the generated Order ID—must execute in **under 5 seconds**.
* **Dashboard Scale:** The merchant data console must comfortably render tables populated with up to 500 comprehensive records in **under 3 seconds**.
* **Concurrency Metrics:** The system infrastructure must natively sustain a baseline performance profile of **50 concurrent active users** without degradation.

#### 5.2 Information Security & System Hardening
* **Data Encryption at Rest:** All sensitive personal data points, specifically buyer phone numbers and granular delivery addresses, must be encrypted at rest using the **AES-256** standard.
* **Passwordless Security Policy:** Passwords are fully excluded from the system schema. Authentication relies exclusively on dynamically generated OTP layers.
* **OTP Lifecycle Constraints:** Every generated OTP token must expire exactly **5 minutes** after creation and must be cryptographically invalidated immediately upon its initial utilization attempt.
* **Route Access Controls:** All administrative endpoints, data fetch requests, and status adjustment operations within the seller namespace require an active, validated session signature.
* **Rate-Limiting Matrix:**
    * *Transaction Throttling:* Maximum of **10 checkout orders per minute** per individual buyer footprint.
    * *Authentication Throttling:* Maximum of **5 OTP generation requests** per individual phone number per hour.

#### 5.3 System Availability
* **Uptime SLA:** The platform core architecture must target a rolling availability matrix of **99.5% uptime**, excluding pre-announced system maintenance windows.

#### 5.4 Auditing & Logging Architecture
* **State Audits:** The backend framework must generate structured logs for every individual order status transition. Each log line must append an absolute timestamp, the originating state, the destination state, and the specific acting entity signature (e.g., a specific seller ID or system automated trigger).

---

### 6. Scope Clarifications & Boundaries

#### 🛑 Explicitly Out of Scope (MVP Roadmap Contract)
To maintain velocity, safety, and clear developmental constraints for the initial release (v1), the following blocks are formally excluded from active development:
1.  **Payment Gateway Rails:** Direct integrated processing for localized networks (such as Telebirr, Chapa, or direct banking webhooks) is excluded. Transactions assume manual/cash-on-delivery structures.
2.  **Automated Inventory Controls:** No systemic auto-deductions of quantitative stock fields upon checkout.
3.  **Multi-Vendor Marketplaces:** Independent merchants utilize distinct subdomains or paths; no cross-vendor discovery engines will be built.
4.  **Complex Variants:** Deep nested variant combinations beyond the basic standalone *Size* and *Color* fields are unsupported.
5.  **Bulk Upload Utilities:** Merchants cannot perform batch updates or CSV/Excel catalog uploads.
6.  **Buyer Registrations:** There are no buyer accounts, profile tabs, or password-protected buyer portals.
7.  **Real-Time Chat Systems:** Inter-user messaging or embedded customer support text fields are entirely omitted.
8.  **Multi-Tenant Architectures:** Infrastructure is optimized around standard distributed standalone deployments rather than a singular cluster-wide shared database layout.
9.  **Persistent Shopping Carts:** Single-product direct checkout routing replaces a multi-item persistent shopping bag experience.

---

### 7. Dependencies, Risks & Risk Mitigation Strategy

| Identified Risk Area | Core Structural Dependency | Proactive Mitigation Strategy |
| :--- | :--- | :--- |
| **Hosting Infrastructure Costs** | Infrastructure hosting models for MVP deployment. | Restrict framework footprints to fit within dependable free-tier compute layers (e.g., GitHub, Vercel, Railway). Maintain secondary backup host configurations. |
| **Domain Registration Access** | DNS Routing and top-level URL procurement. | Explicitly waive custom domain prerequisites for v1. Provision accounts under highly accessible, free canonical subdomains. |
| **Notification Pipeline Friction** | SMS/Telegram messaging gateways for tracking updates. | Source scalable local SMS gateways (such as AfroMessage) and Telegram bot webhooks offering robust complimentary free tiers. |
| **Mobile Network Degradation** | End-user mobile bandwidth constraints (Ethiopian 3G/4G networks). | Engineer an extraordinarily lightweight frontend framework completely devoid of heavy client-side scripts. Enforce automated compression pipelines restricting all product image files to `< 200KB` alongside lazy-loading logic. |
| **Low Merchant Adoption** | Core customer system engagement. | Run early beta-testing loops with the three initial interviewed local merchants, granting exclusive premium configurations and hands-on instructional support. |
| **Checkout Abandonment** | Buyer UX friction within forms. | Enforce a hard maximum of 3 highly intuitive, input-masked text fields during checkouts. Complete end-to-end usability tests with 5 neutral buyers prior to release. |
| **Dashboard Abandonment** | Merchant order visibility and attention span. | Institute structural day-start operational training for early merchants and hook up automated daily digest notification summaries via Telegram bots. |
| **Static Asset Bloat** | Media latency on slower networks. | Programmatically bundle media operations to compress assets down below `< 200KB` on import and offload serving to a high-speed free Content Delivery Network (Cloudinary). |
| **Scope Creep / Feature Creep** | Development timeline bloating. | Treat the *Out of Scope* section of this document as a binding contractual mandate. Deflect all enhancement suggestions to post-v1 planning. |
| **Free-Tier Database Availability** | Operational persistence on Supabase tiers. | Restrict transactional overhead. Configure automated cron routines to generate structural CSV database dumps weekly, dispatching them to developer backups to neutralize data loss. |