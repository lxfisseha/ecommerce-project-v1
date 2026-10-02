# Seed images

Drop product photos here and reference them from `PRODUCT_TEMPLATES` in
`src/scripts/seed_products.py` as `local:<filename.ext>`.

```
src/seed_assets/
  gym-gloves.png
  handgrip.png
  knee-sleeve.png
```

The three names above are the ones the sportwear catalogue currently expects,
for products with no usable stock photography:

- `gym-gloves.png` — Leather Gym Gloves
- `handgrip.png` — Hand Grip Strengthener
- `knee-sleeve.png` — Knee Support Sleeve

Anything else in the catalogue uses a remote stock photo listed in
`PRODUCT_TEMPLATES`, so this folder only needs the products stock sites do not
cover well.

A missing file is logged as a warning and that product is seeded without an
image rather than failing the run, so a partial folder still produces a usable
catalogue. Every image is stored through the same path as a real upload and
queued for WebP variant generation, so a seeded product behaves exactly like one
a seller added by hand.

Images are not tracked in git: they are photographs, and adding binary blobs to
the repository bloats it for anyone who only wants the code.
