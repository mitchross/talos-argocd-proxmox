# LLM comparison 20261103T233447Z

Gateway `http://litellm-service.litellm.svc.cluster.local:4000/v1` · thinking `off` · repeats 3 · started 2026-11-03 23:34:47Z

Client-side timings through LiteLLM; medians over repeats. prefill tok/s = prompt tokens / TTFT.

| Prompt | Model | TTFT s | Prefill tok/s | Decode tok/s | Total s | Prompt tok | Output tok | Finish | Errors |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| short-chat | qwen3.8-27b | 0.39 | 194.9 | 40.22 | 3.18 | 76 | 109 | stop | 0 |
| prefill-8k | qwen3.8-27b | 6.42 | 969.8 | 57.23 | 6.59 | 6227 | 8 | stop ✓needle | 0 |
| coding | qwen3.8-27b | 0.26 | 559.8 | 39.7 | 26.59 | 145 | 1019 | stop | 0 |
| reverse-engineering | qwen3.8-27b | 0.4 | 585.4 | 39.3 | 25.24 | 233 | 972 | stop | 0 |

## Outputs (first repeat)

### Short chat (`short-chat`)

<table><tr><th>qwen3.8-27b</th></tr><tr>
<td valign="top"><pre>A Kubernetes Deployment manages a set of identical, stateless Pods where each instance is interchangeable and can be scaled or replaced independently, making it ideal for web servers or APIs. In contrast, a StatefulSet provides stable network identities, persistent storage, and ordered deployment guarantees for each Pod, which is essential for applications requiring consistent data or unique identifiers like databases. You should choose a Deployment for scalable, stateless workloads, while reserving StatefulSets for stateful services that require durable storage and specific pod ordering.</pre></td>
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
        raise ValueError(f&quot;Invalid quantity: no numeric part in &#x27;{s}&#x27;&quot;)

    try:
        value = float(numeric_part)
    except ValueError:
        raise ValueError(f&quot;Invalid numeric part in &#x27;{s}&#x27;&quot;)

    return value * multiplier


class TestParseQuantity(unittest.TestCase):

    def test_binary_suffixes(self):
        self.assertEqual(parse_quantity(&#x27;1Ki&#x27;), 1024.0)
        self.assertEqual(parse_quantity(&#x27;1Mi&#x27;), 1024 ** 2)
        self.assertEqual(parse_quantity(&#x27;1Gi&#x27;), 1024 ** 3)
        self.assertEqual(parse_quantity(&#x27;1Ti&#x27;), 1024 ** 4)
        self.assertEqual(parse_quantity(&#x27;1Pi&#x27;), 1024 ** 5)
        self.assertEqual(parse_quantity(&#x27;1Ei&#x27;), 1024 ** 6)

    def test_decimal_suffixes(self):
        self.assertEqual(parse_quantity(&#x27;1n&#x27;), 1e-9)
        self.assertEqual(parse_quantity(&#x27;1u&#x27;), 1e-6)
        self.assertEqual(parse_quantity(&#x27;1m&#x27;), 1e-3)
        self.assertEqual(parse_quantity(&#x27;1k&#x27;), 1e3)
        self.assertEqual(parse_quantity(&#x27;1M&#x27;), 1e6)
        self.assertEqual(parse_quantity(&#x27;1G&#x27;), 1e9)
        self.assertEqual(parse_quantity(&#x27;1T&#x27;), 1e12)
        self.assertEqual(parse_quantity(&#x27;1P&#x27;), 1e15)
        self.assertEqual(parse_quantity(&#x27;1E&#x27;), 1e18)

    def test_plain_integers_and_decimals(self):
        self.assertEqual(parse_quantity(&#x27;42&#x27;), 42.0)
        self.assertEqual(parse_quantity(&#x27;3.14&#x27;), 3.14)
        self.assertEqual(parse_quantity(&#x27;-7&#x27;), -7.0)
        self.assertEqual(parse_quantity(&#x27;0.5&#x27;), 0.5)

    def test_exponent_form(self):
        self.assertEqual(parse_quantity(&#x27;2e3&#x27;), 2000.0)
        self.assertAlmostEqual(parse_quantity(&#x27;1.5e2&#x27;), 150.0)
        self.assertAlmostEqual(parse_quantity(&#x27;3e-2&#x27;), 0.03)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            parse_quantity(&#x27;&#x27;)
        with self.assertRaises(ValueError):
            parse_quantity(&#x27;abc&#x27;)


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
        // Note: ROL on 8-bit integer: ((val &lt;&lt; 3) | (val &gt;&gt; 5)) &amp; 0xFF
        val = ((val &lt;&lt; 3) | (val &gt;&gt; 5)) &amp; 0xFF;
        
        buffer[i] = val;
    }
}
```

---

### 3. Purpose of the 8-byte Table at `rdx`

The table at `rdx` is a **repeating XOR key** (or keystream segment). 

*   Since the index is calculated as `eax &amp; 7` (where `eax` is the loop counter), the table cycles every 8 bytes.
*   This means the first 8 bytes of the table are applied to positions 0–7, the same 8 bytes are applied to positions 8–15, and so on.
*   It acts as a **Vigenère-like cipher key** but with XOR instead of addition/subtraction modulo 256. The &quot;period&quot; of the key is 8 bytes.

---

### 4. Function that Undoes the Transformation (Encryption/Encode)

To reverse the transformation, we must apply the inverse operations in reverse order:
1.  The forward operation was: `out = ROL(3, (in ^ key))`
2.  To invert:
    *   First, undo the rotation: `ROL^{-1}(3)` is equivalent to `ROR(3)` (Rotate Right by 3).
    *   Then, undo the XOR: XOR is its own inverse, so `in = out ^ key`.

Thus, the inverse operation is: `in = ROR(3, out) ^ key`

Here is the C code for the inverse function (`encode`):

```c
#include &lt;stdint.h&gt;
#include &lt;stddef.h&gt;

/**
 * Reverses the &#x27;decode&#x27; function.
 * Applies ROR(3) then XOR with the key table.
 */
void encode(uint8_t *buffer, size_t length, const uint8_t *key_table) {
    if (length == 0) return;

    for (size_t i = 0; i &lt; length; i++) {
        uint8_t val = buffer[i];
        
        // Key byte is the same as in decode: key_table[i &amp; 7]
        uint8_t key_byte = key_table[i &amp; 7];
        
        // Inverse of ROL(3) is ROR(3)
        // ROR 3: ((val &gt;&gt; 3) | (val &lt;&lt; 5)) &amp; 0xFF
        val = ((val &gt;&gt; 3) | (val &lt;&lt; 5)) &amp; 0xFF;
        
        // XOR is self-inverse
        val ^= key_byte;
        
        buffer[i] = val;
    }
}
```

### Verification Example

Let’s verify with a simple case:
*   `key_table[0] = 0x01`
*   Input byte at index 0: `0x00`

**Decode:**
1.  `val = 0x00`
2.  `key = 0x01`
3.  `val ^= key` → `0x01`
4.  `ROL(3, 0x01)` → `0x08`
5.  Output: `0x08`

**Encode (Undo):**
1.  `val = 0x08`
2.  `key = 0x01`
3.  `ROR(3, 0x08)` → `0x01`
4.  `val ^= key` → `0x01 ^ 0x01 = 0x00`
5.  Output: `0x00` ✅ Matches original input.</pre></td>
</tr></table>

