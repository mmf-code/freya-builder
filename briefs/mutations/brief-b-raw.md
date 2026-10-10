# Freya Bank: material for calls on more than one late product

Freya Bank is fictional. Every customer, debt and payment here is synthetic.

Two documents follow, as the bank sent them: a short e-mail and a change notice to the contact policy. They extend
the material for the early-stage collections assistant (the e-mail, Contact Policy CP-4, memo OPS-2026-41 and the
close code list). Everything in that material still applies unless the change notice below replaces it.

---

## Document 5: e-mail

From: Collections Operations, Freya Bank
To: Digital assistant team
Subject: Customers who are late on two or three products

Hello,

Some customers are now late on more than one product, never more than three. The assistant calls them under the same
policy, with the changes in the notice below. The biggest change for you: on these calls the assistant leaves a note
with `add_note` for every product that ends without a promise, so the close code list's line about `add_note` no
longer holds for them. Please read the whole notice; the order of the steps matters.

Thanks,
Collections Operations

---

## Document 6: Change notice CN-12 to CP-4 (customers late on one to three products)

### A. What the assistant gets and says

A1. `get_account` returns between one and three products. Every product has its own `past_due`, its own `days_late`
and its own floor.

A2. Before it asks the customer for anything, the assistant states every late product, in one sentence per product.

A3. The stage and the PTP deadline (CP-4 2.5 b, as changed by OPS-2026-41) are worked out for each product on its
own, from that product's `days_late`. The same customer can therefore have products with different deadlines.

### B. Getting the PTPs

B1. The first ask covers all products at once: can the customer pay all of them today? If not, the assistant takes
the products one at a time, in the order in which `get_account` returned them, and does not ask about today again
for each product. Every product starts at the first persuasion attempt of CP-4 2.7 b).

B2. Persuasion attempts are counted separately for each product.

B3. When the customer names one date for everything and that date is after the deadline of one of the products, that
product is recorded on its own deadline, and the read-back says so. The other products keep the date the customer
named.

B4. A dispute (CP-4 2.8 f) or an "I already paid" (CP-4 2.8 e) about one product does not end the call. The assistant
notes it for that product and goes on with the others.

### C. Confirming, recording and notes

C1. The assistant reads all the PTPs back together and asks for one confirmation. After that it calls
`create_promise` once for each product.

C2. A customer may promise some products and refuse others. For every product that ends without a PTP, the assistant
calls `add_note` with that product's `product_id` and one reason: `refused`, `hardship`, `dispute`, `paid` or
`service_error`. This also applies when no product gets a PTP.

C3. If `create_promise` fails twice for one product, the PTPs already recorded stay, and the assistant calls
`add_note` with reason `service_error` for the product that failed.

### D. Transfers

D1. A request for a new plan or lower instalments still transfers the call (CP-4 2.8 c). PTPs recorded before the
request stay; PTPs agreed but not yet recorded are not recorded. The call closes as transferred, restructuring.

D2. On every transfer (restructuring, support or human), the assistant adds no notes at all, neither before nor after
the transfer.

### E. Close codes on these calls

The close code list still applies. With more than one product, `promise` is used whenever at least one PTP was
recorded, except in the case of D1. When no PTP was recorded: if every product was noted `paid`, the call closes as
`paid`; otherwise it closes as `no_promise` with the reason of the first product, in `get_account` order, whose note
is not `paid`.
