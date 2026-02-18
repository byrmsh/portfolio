---
title: Anvil Compression
description: Lossless compression desktop app built around LZ77 + Huffman ideas.
summary: Python + PyQt desktop utility for compressing and decompressing text/document files with a custom algorithm pipeline.
year: 2020
stack:
  - Python
  - PyQt6
  - LZ77
  - Huffman Coding
heroImage: /projects/anvil-compression/SS1.png
galleryImages:
  - /projects/anvil-compression/SS1.png
order: 9
---

Anvil Compression started as an algorithm experiment and became a full desktop utility. I combined LZ77 and Huffman stages, then wrapped the flow in a usable GUI.

You pick source and destination, run encode/decode, and the app handles the rest. The implementation is simple by design, but strict about correctness and file-handling edge cases.

It was one of my earliest "turn theory into a usable product" projects.
