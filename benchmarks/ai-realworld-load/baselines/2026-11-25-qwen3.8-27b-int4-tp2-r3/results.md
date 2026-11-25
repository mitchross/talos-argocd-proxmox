# LLM comparison 20261125T165102Z

Gateway `http://vllm-service.vllm.svc:8080/v1` · thinking `off` · repeats 3 · started 2026-11-25 16:51:02Z

Client-side timings straight to the vLLM Service (no LiteLLM hop); medians over repeats. prefill tok/s = prompt tokens / TTFT.

| Prompt | Model | TTFT s | Prefill tok/s | Decode tok/s | Total s | Prompt tok | Output tok | Finish | Errors |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| short-chat | qwen3.8-27b | 0.36 | 212.9 | 63.21 | 2.26 | 76 | 118 | stop | 0 |
| prefill-8k | qwen3.8-27b | 4.21 | 1477.3 | 88.75 | 4.32 | 6227 | 8 | stop ✓needle | 0 |
| coding | qwen3.8-27b | 0.29 | 505.2 | 62.89 | 18.79 | 145 | 1157 | stop | 0 |
| reverse-engineering | qwen3.8-27b | 0.41 | 571.1 | 62.74 | 17.4 | 233 | 1065 | stop | 0 |

## Outputs (first repeat)

### Short chat (`short-chat`)

<table><tr><th>qwen3.8-27b</th></tr><tr>
<td valign="top"><pre>A Kubernetes Deployment manages a set of identical, stateless pods where individual instances are interchangeable and can be scaled or replaced without concern for their specific identity. In contrast, a StatefulSet provides each pod with a stable, unique network identity (hostname) and persistent storage that remains attached to the pod even if it is rescheduled. You should choose a Deployment for general web services or microservices that do not require specific data persistence or ordering, while opting for a StatefulSet when running databases, distributed caches, or other applications that depend on consistent identities and durable storage across restarts.</pre></td>
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
    &quot;&quot;&quot;
    Convert Kubernetes resource quantities to a plain number.
    
    Supports:
    - Binary suffixes: Ki, Mi, Gi, Ti, Pi, Ei
    - Decimal suffixes: n, u, m, k, M, G, T, P, E
    - Plain integers and decimals
    - Exponent forms (e.g., 2e3)
    
    Raises ValueError on bad input.
    &quot;&quot;&quot;
    if not isinstance(s, str):
        raise ValueError(&quot;Input must be a string&quot;)
    
    s = s.strip()
    if not s:
        raise ValueError(&quot;Empty string is not valid&quot;)
    
    # Check for exponent form first
    if &#x27;e&#x27; in s or &#x27;E&#x27; in s:
        try:
            return float(s)
        except ValueError:
            raise ValueError(f&quot;Invalid quantity: {s}&quot;)
    
    # Try to match suffix
    # Binary suffixes
    binary_suffixes = {
        &#x27;Ki&#x27;: 1024,
        &#x27;Mi&#x27;: 1024**2,
        &#x27;Gi&#x27;: 1024**3,
        &#x27;Ti&#x27;: 1024**4,
        &#x27;Pi&#x27;: 1024**5,
        &#x27;Ei&#x27;: 1024**6,
    }
    
    # Decimal suffixes
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
    
    # Check binary suffixes first (they are two characters)
    for suffix, multiplier in binary_suffixes.items():
        if s.endswith(suffix):
            num_str = s[:-len(suffix)]
            if not num_str:
                raise ValueError(f&quot;Missing number before suffix: {s}&quot;)
            try:
                return float(num_str) * multiplier
            except ValueError:
                raise ValueError(f&quot;Invalid quantity: {s}&quot;)
    
    # Check decimal suffixes (single character)
    for suffix, multiplier in decimal_suffixes.items():
        if len(s) &gt; 1 and s[-1] == suffix:
            num_str = s[:-1]
            if not num_str:
                raise ValueError(f&quot;Missing number before suffix: {s}&quot;)
            try:
                return float(num_str) * multiplier
            except ValueError:
                raise ValueError(f&quot;Invalid quantity: {s}&quot;)
    
    # No suffix found, try to parse as plain number
    try:
        return float(s)
    except ValueError:
        raise ValueError(f&quot;Invalid quantity: {s}&quot;)


class TestParseQuantity(unittest.TestCase):
    def test_binary_suffixes(self):
        self.assertEqual(parse_quantity(&quot;1Ki&quot;), 1024.0)
        self.assertEqual(parse_quantity(&quot;2Mi&quot;), 2 * 1024**2)
        self.assertEqual(parse_quantity(&quot;3Gi&quot;), 3 * 1024**3)
        self.assertEqual(parse_quantity(&quot;4Ti&quot;), 4 * 1024**4)
        self.assertEqual(parse_quantity(&quot;5Pi&quot;), 5 * 1024**5)
        self.assertEqual(parse_quantity(&quot;6Ei&quot;), 6 * 1024**6)
    
    def test_decimal_suffixes(self):
        self.assertAlmostEqual(parse_quantity(&quot;1n&quot;), 1e-9)
        self.assertAlmostEqual(parse_quantity(&quot;2u&quot;), 2e-6)
        self.assertAlmostEqual(parse_quantity(&quot;3m&quot;), 3e-3)
        self.assertAlmostEqual(parse_quantity(&quot;4k&quot;), 4e3)
        self.assertAlmostEqual(parse_quantity(&quot;5M&quot;), 5e6)
        self.assertAlmostEqual(parse_quantity(&quot;6G&quot;), 6e9)
        self.assertAlmostEqual(parse_quantity(&quot;7T&quot;), 7e12)
        self.assertAlmostEqual(parse_quantity(&quot;8P&quot;), 8e15)
        self.assertAlmostEqual(parse_quantity(&quot;9E&quot;), 9e18)
    
    def test_plain_numbers(self):
        self.assertEqual(parse_quantity(&quot;42&quot;), 42.0)
        self.assertEqual(parse_quantity(&quot;3.14&quot;), 3.14)
        self.assertEqual(parse_quantity(&quot;-5&quot;), -5.0)
        self.assertEqual(parse_quantity(&quot;0.5&quot;), 0.5)
    
    def test_exponent_form(self):
        self.assertEqual(parse_quantity(&quot;2e3&quot;), 2000.0)
        self.assertEqual(parse_quantity(&quot;1.5E2&quot;), 150.0)
        self.assertEqual(parse_quantity(&quot;3e-2&quot;), 0.03)
    
    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            parse_quantity(&quot;&quot;)
        with self.assertRaises(ValueError):
            parse_quantity(&quot;abc&quot;)
        with self.assertRaises(ValueError):
            parse_quantity(&quot;12xyz&quot;)
        with self.assertRaises(ValueError):
            parse_quantity(&quot;Ki&quot;)


if __name__ == &quot;__main__&quot;:
    unittest.main()</pre></td>
</tr></table>

### Reverse-engineering explanation (`reverse-engineering`)

<table><tr><th>qwen3.8-27b</th></tr><tr>
<td valign="top"><pre>Here is the analysis of the provided x86-64 assembly function.

### 1. C Prototype and Argument Roles

Based on the System V ABI for x86-64:
*   `rdi`: First argument (pointer to data buffer)
*   `rsi`: Second argument (length/size in bytes)
*   `rdx`: Third argument (pointer to a lookup table)

**C Prototype:**
```c
void transform(uint8_t *buf, size_t len, const uint8_t *table);
```

**Argument Roles:**
*   **`buf` (`rdi`)**: The input/output buffer containing the data to be transformed. It is modified in place.
*   **`len` (`rsi`)**: The number of bytes in `buf` to process.
*   **`table` (`rdx`)**: A pointer to an 8-byte array used as a key or transformation matrix.

---

### 2. Equivalent C Code

The assembly implements a loop that iterates through each byte of the buffer. For each byte at index `i`:
1.  Read the byte from `buf[i]`.
2.  Determine the index into the table using `i % 8` (via `and r8d, 7`).
3.  XOR the current byte with `table[i % 8]`.
4.  Rotate the result left by 3 bits (via `rol cl, 3`).
5.  Store the result back into `buf[i]`.

**Equivalent C Code:**
```c
#include &lt;stdint.h&gt;
#include &lt;stddef.h&gt;

void transform(uint8_t *buf, size_t len, const uint8_t *table) {
    if (len == 0) return; // test rsi, rsi / je .done

    for (size_t i = 0; i &lt; len; i++) {
        uint8_t val = buf[i];
        uint8_t key = table[i &amp; 7]; // i % 8
        val ^= key;
        // Rotate left by 3 bits
        val = (val &lt;&lt; 3) | (val &gt;&gt; 5);
        buf[i] = val;
    }
}
```

---

### 3. Purpose of the 8-byte Table at `rdx`

The 8-byte table acts as a **repeating XOR key**. 

Because the index into the table is calculated as `i &amp; 7` (which is equivalent to `i % 8`), the same 8-byte sequence is applied cyclically across the entire buffer. This means:
*   Byte 0, 8, 16, ... are XORed with `table[0]`
*   Byte 1, 9, 17, ... are XORed with `table[1]`
*   ...
*   Byte 7, 15, 23, ... are XORed with `table[7]`

This creates a simple stream cipher-like effect where the &quot;key&quot; repeats every 8 bytes.

---

### 4. Function That Undoes the Transformation

To reverse the transformation, we must apply the inverse operations in reverse order. The original operation was:
$$ \text{out} = \text{ROL}_3(\text{in} \oplus \text{key}) $$

To invert this:
1.  **Reverse Rotation**: Rotate right by 3 bits (equivalent to rotating left by 5).
2.  **Reverse XOR**: XOR with the same key (since $A \oplus B \oplus B = A$).

**Inverse C Function:**
```c
#include &lt;stdint.h&gt;
#include &lt;stddef.h&gt;

void untransform(uint8_t *buf, size_t len, const uint8_t *table) {
    if (len == 0) return;

    for (size_t i = 0; i &lt; len; i++) {
        uint8_t val = buf[i];
        uint8_t key = table[i &amp; 7];
        
        // Reverse the rotation: ROL 3 -&gt; ROR 3
        val = (val &gt;&gt; 3) | (val &lt;&lt; 5);
        
        // Reverse the XOR
        val ^= key;
        
        buf[i] = val;
    }
}
```

**Key Insight:** Since XOR is its own inverse ($a \oplus k \oplus k = a$) and rotation is also its own inverse when applied in the opposite direction (or the complementary direction modulo 8), applying the exact same logic but with **ROR 3** instead of **ROL 3** will restore the original data.</pre></td>
</tr></table>

