# LLM comparison 20261103T233254Z

Gateway `http://litellm-service.litellm.svc.cluster.local:4000/v1` · thinking `off` · repeats 1 · started 2026-11-03 23:32:54Z

Client-side timings through LiteLLM; medians over repeats. prefill tok/s = prompt tokens / TTFT.

| Prompt | Model | TTFT s | Prefill tok/s | Decode tok/s | Total s | Prompt tok | Output tok | Finish | Errors |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| short-chat | qwen3.8-27b | 0.35 | 217.8 | 41.84 | 3.52 | 76 | 131 | stop | 0 |
| prefill-8k | qwen3.8-27b | 6.38 | 976.2 | 58.35 | 6.55 | 6227 | 8 | stop ✓needle | 0 |
| coding | qwen3.8-27b | 0.25 | 573.1 | 41.35 | 25.03 | 145 | 1021 | stop | 0 |
| reverse-engineering | qwen3.8-27b | 0.43 | 546.9 | 40.62 | 30.29 | 233 | 1209 | stop | 0 |

## Outputs (first repeat)

### Short chat (`short-chat`)

<table><tr><th>qwen3.8-27b</th></tr><tr>
<td valign="top"><pre>A Kubernetes Deployment manages a set of identical, stateless Pods where each instance is interchangeable and can be scaled or replaced independently, making it ideal for web servers or microservices that do not require persistent data or unique identities. In contrast, a StatefulSet provides stable network identifiers (unique names and DNS records) and ordered deployment or scaling guarantees, ensuring that specific Pod instances always bind to the same persistent storage volumes. You should choose a Deployment for scalable, stateless applications like APIs or frontends, while reserving StatefulSets for stateful workloads such as databases, message queues, or distributed systems that rely on consistent identity and data persistence.</pre></td>
</tr></table>

### 8K-context prefill (needle recall) (`prefill-8k`)

<table><tr><th>qwen3.8-27b</th></tr><tr>
<td valign="top"><pre>JADE-4471</pre></td>
</tr></table>

### Coding task (`coding`)

<table><tr><th>qwen3.8-27b</th></tr><tr>
<td valign="top"><pre>```python
import unittest


def parse_quantity(s: str) -&gt; float:
    &quot;&quot;&quot;Convert Kubernetes resource quantity to a plain number.&quot;&quot;&quot;
    if not isinstance(s, str):
        raise ValueError(&quot;Input must be a string&quot;)

    s = s.strip()
    if not s:
        raise ValueError(&quot;Empty string&quot;)

    # Define suffix multipliers
    binary_suffixes = {
        &#x27;Ki&#x27;: 1024 ** 1,
        &#x27;Mi&#x27;: 1024 ** 2,
        &#x27;Gi&#x27;: 1024 ** 3,
        &#x27;Ti&#x27;: 1024 ** 4,
        &#x27;Pi&#x27;: 1024 ** 5,
        &#x27;Ei&#x27;: 1024 ** 6,
    }

    decimal_suffixes = {
        &#x27;n&#x27;: 1e-9,
        &#x27;u&#x27;: 1e-6,
        &#x27;m&#x27;: 1e-3,
        &#x27;k&#x27;: 1e3,
        &#x27;M&#x27;: 1e6,
        &#x27;G&#x27;: 1e9,
        &#x27;T&#x27;: 1e12,
        &#x27;P&#x27;: 1e15,
        &#x27;E&#x27;: 1e18,
    }

    # Check for binary suffixes first (two chars)
    multiplier = 1.0
    numeric_part = s

    found_suffix = False
    for suffix in [&#x27;Ki&#x27;, &#x27;Mi&#x27;, &#x27;Gi&#x27;, &#x27;Ti&#x27;, &#x27;Pi&#x27;, &#x27;Ei&#x27;]:
        if s.endswith(suffix):
            numeric_part = s[:-len(suffix)]
            multiplier = binary_suffixes[suffix]
            found_suffix = True
            break

    if not found_suffix:
        # Check for decimal suffixes (one char)
        for suffix in [&#x27;n&#x27;, &#x27;u&#x27;, &#x27;m&#x27;, &#x27;k&#x27;, &#x27;M&#x27;, &#x27;G&#x27;, &#x27;T&#x27;, &#x27;P&#x27;, &#x27;E&#x27;]:
            if s.endswith(suffix):
                numeric_part = s[:-len(suffix)]
                multiplier = decimal_suffixes[suffix]
                found_suffix = True
                break

    # Parse the numeric part
    numeric_part = numeric_part.strip()
    if not numeric_part:
        raise ValueError(f&quot;Invalid quantity: &#x27;{s}&#x27;&quot;)

    try:
        value = float(numeric_part)
    except ValueError:
        raise ValueError(f&quot;Invalid numeric part: &#x27;{numeric_part}&#x27; in quantity &#x27;{s}&#x27;&quot;)

    return value * multiplier


class TestParseQuantity(unittest.TestCase):
    def test_binary_suffixes(self):
        self.assertEqual(parse_quantity(&#x27;1Ki&#x27;), 1024.0)
        self.assertEqual(parse_quantity(&#x27;2Mi&#x27;), 2 * 1024 ** 2)
        self.assertEqual(parse_quantity(&#x27;3Gi&#x27;), 3 * 1024 ** 3)
        self.assertEqual(parse_quantity(&#x27;4Ti&#x27;), 4 * 1024 ** 4)
        self.assertEqual(parse_quantity(&#x27;5Pi&#x27;), 5 * 1024 ** 5)
        self.assertEqual(parse_quantity(&#x27;6Ei&#x27;), 6 * 1024 ** 6)

    def test_decimal_suffixes(self):
        self.assertAlmostEqual(parse_quantity(&#x27;1n&#x27;), 1e-9)
        self.assertAlmostEqual(parse_quantity(&#x27;2u&#x27;), 2e-6)
        self.assertAlmostEqual(parse_quantity(&#x27;3m&#x27;), 3e-3)
        self.assertAlmostEqual(parse_quantity(&#x27;4k&#x27;), 4e3)
        self.assertAlmostEqual(parse_quantity(&#x27;5M&#x27;), 5e6)
        self.assertAlmostEqual(parse_quantity(&#x27;6G&#x27;), 6e9)
        self.assertAlmostEqual(parse_quantity(&#x27;7T&#x27;), 7e12)
        self.assertAlmostEqual(parse_quantity(&#x27;8P&#x27;), 8e15)
        self.assertAlmostEqual(parse_quantity(&#x27;9E&#x27;), 9e18)

    def test_plain_integers_and_decimals(self):
        self.assertEqual(parse_quantity(&#x27;123&#x27;), 123.0)
        self.assertAlmostEqual(parse_quantity(&#x27;1.5&#x27;), 1.5)
        self.assertAlmostEqual(parse_quantity(&#x27;0.001&#x27;), 0.001)

    def test_exponent_form(self):
        self.assertAlmostEqual(parse_quantity(&#x27;2e3&#x27;), 2000.0)
        self.assertAlmostEqual(parse_quantity(&#x27;1.5e2&#x27;), 150.0)
        self.assertAlmostEqual(parse_quantity(&#x27;3e-2&#x27;), 0.03)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            parse_quantity(&#x27;abc&#x27;)
        with self.assertRaises(ValueError):
            parse_quantity(&#x27;12X&#x27;)


if __name__ == &#x27;__main__&#x27;:
    unittest.main()
```</pre></td>
</tr></table>

### Reverse-engineering explanation (`reverse-engineering`)

<table><tr><th>qwen3.8-27b</th></tr><tr>
<td valign="top"><pre>Here is the analysis of the provided x86-64 assembly function.

### 1. C Prototype with Argument Roles

```c
void decode(uint8_t *buffer, size_t length, const uint8_t *key_table);
```

*   **`rdi` (`buffer`)**: Pointer to the data buffer to be modified in-place.
*   **`rsi` (`length`)**: The number of bytes in the buffer to process.
*   **`rdx` (`key_table`)**: Pointer to an 8-byte lookup table used for decryption.

---

### 2. Equivalent C Code

The assembly implements a byte-wise decryption loop. For each byte in the buffer:
1.  It reads the current byte.
2.  It calculates an index into the key table using the lower 3 bits of the current byte position (i.e., `position % 8`).
3.  It XORs the byte with the corresponding key byte.
4.  It rotates the result left by 3 bits.
5.  It stores the result back into the buffer.

```c
#include &lt;stdint.h&gt;
#include &lt;stddef.h&gt;

void decode(uint8_t *buffer, size_t length, const uint8_t *key_table) {
    if (length == 0) return; // test rsi, rsi / je .done

    for (size_t i = 0; i &lt; length; i++) {
        uint8_t val = buffer[i];
        
        // Index into the 8-byte key table using the lower 3 bits of the index
        uint8_t key_byte = key_table[i &amp; 7];
        
        // XOR with key
        val ^= key_byte;
        
        // Rotate Left by 3 bits
        // Note: ROL on a byte wraps around. 
        // In C: ((val &lt;&lt; 3) | (val &gt;&gt; 5)) &amp; 0xFF
        val = (val &lt;&lt; 3) | (val &gt;&gt; 5);
        
        buffer[i] = val;
    }
}
```

---

### 3. What is the 8-byte table at `rdx` for?

The 8-byte table at `rdx` is a **repeating XOR key** (also known as a Vigenère cipher key or keystream).

*   The instruction `and r8d, 7` masks the loop counter (`rax`) with `7` (binary `111`). This effectively computes `i % 8`.
*   This means the key repeats every 8 bytes. The first byte of the buffer is XORed with `key_table[0]`, the second with `key_table[1]`, ..., the eighth with `key_table[7]`, and the ninth again with `key_table[0]`.
*   This is a common technique in simple ciphers to avoid using a single repeating byte, providing slightly more diffusion than a monoalphabetic substitution while remaining computationally cheap.

---

### 4. Function that Undoes the Transformation (Encryption/Inverse)

To reverse the transformation, we must apply the inverse operations in reverse order.

**Original Operation per byte:**
1.  `val = buffer[i]`
2.  `val = val ^ key[i%8]`
3.  `val = ROL(val, 3)`
4.  `buffer[i] = val`

**Inverse Operation per byte:**
1.  `val = buffer[i]` (which is the encrypted value)
2.  `val = ROR(val, 3)` (Inverse of ROL 3 is ROR 3)
3.  `val = val ^ key[i%8]` (XOR is its own inverse)
4.  `buffer[i] = val`

#### C Code for the Inverse Function (`encode`):

```c
#include &lt;stdint.h&gt;
#include &lt;stddef.h&gt;

void encode(uint8_t *buffer, size_t length, const uint8_t *key_table) {
    if (length == 0) return;

    for (size_t i = 0; i &lt; length; i++) {
        uint8_t val = buffer[i];
        
        // Step 1: Reverse the rotation (Rotate Right by 3)
        // ROR 3: (val &gt;&gt; 3) | (val &lt;&lt; 5)
        val = (val &gt;&gt; 3) | (val &lt;&lt; 5);
        
        // Step 2: XOR with the same key byte (XOR is symmetric)
        val ^= key_table[i &amp; 7];
        
        buffer[i] = val;
    }
}
```

#### Assembly for the Inverse Function (Optional, for completeness):

If you wanted to write the inverse in assembly similar to the original:

```asm
encode:
    test    rsi, rsi
    je      .done_enc
.loop_enc:
    movzx   ecx, byte ptr [rdi+rax]
    
    ; ROR cl, 3
    rol     cl, 5       ; ROL 5 is equivalent to ROR 3 for 8-bit values
    
    ; XOR with key
    mov     r8d, eax
    and     r8d, 7
    xor     cl, byte ptr [rdx+r8]
    
    mov     byte ptr [rdi+rax], cl
    inc     rax
    cmp     rax, rsi
    jne     .loop_enc
.done_enc:
    ret
```</pre></td>
</tr></table>

