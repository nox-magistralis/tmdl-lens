# tmdl-lens-test-report

## Overview

| Property | Value |
|---|---|
| **Owner** |  |
| **Team** |  |
| **Refresh Schedule** |  |
| **Last Generated** | 29 March 2026 |

---

## 1. Data Sources

This model contains 2 loaded tables, 1 calculated table, 1 field parameter, 1 measures-only table, 1 calculation group, 1 not loaded, 4 measures, 18 relationships.

| Table | Source Type | Source |
|---|---|---|
| `dim-product` | Power Platform Dataflow | product_dim |
| `fact-sales` | Power BI Dataflow | sales_fact |

### Support Tables

| Table | Type |
|---|---|
| `_measures` | Measures |
| `cg-time-intelligence` | Calculation Group |
| `dim-date` | Calculated (DAX) |
| `param-metric-selector` | Field Parameter |

### Not Loaded

> These tables have `enableLoad = false` and are not visible in the report.
> They are typically used as intermediate query steps.

| Table | Source Type | Source |
|---|---|---|
| `source-sql-staging` | SQL Database | fake-server.database.windows.net / SalesDB / dbo.orders |

---

## 2. Table Details

### `dim-product`

**Source:** Power Platform Dataflow  
**Entity:** `product_dim`  

**Columns**

| Column | Type |
|---|---|
| `product_id` | Text |
| `product_name` | Text |
| `category` | Text |
| `unit_price` | Decimal |

---

### `fact-sales`

**Source:** Power BI Dataflow  
**Entity:** `sales_fact`  

**Columns**

| Column | Type |
|---|---|
| `order_id` | Integer |
| `customer_id` | Text |
| `order_date` | Date/Time |
| `amount` | Decimal |

---

### `cg-time-intelligence`


**Columns**

| Column | Type |
|---|---|
| `Name` | Text |
| `Ordinal` | Integer |

**Calculation Items**

| Item | Ordinal | Format String |
|---|---|---|
| `YTD` | 0 | `SELECTEDMEASUREFORMATSTRING()` |
| `MTD` | 1 | `SELECTEDMEASUREFORMATSTRING()` |
| `Rolling 12M` | 2 | `SELECTEDMEASUREFORMATSTRING()` |
| `Prior Year` | 3 | `SELECTEDMEASUREFORMATSTRING()` |
| `YoY %` | 4 | `0.00%` |

**Item DAX**

**`YTD`**
```dax
TOTALYTD(SELECTEDMEASURE(), 'dim-date'[Date])
```

**`MTD`**
```dax
TOTALMTD(SELECTEDMEASURE(), 'dim-date'[Date])
```

**`Rolling 12M`**
```dax
CALCULATE(
    SELECTEDMEASURE(),
    DATESINPERIOD('dim-date'[Date], LASTDATE('dim-date'[Date]), -12, MONTH)
)
```

**`Prior Year`**
```dax
CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('dim-date'[Date]))
```

**`YoY %`**
```dax
DIVIDE(
    SELECTEDMEASURE() - CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('dim-date'[Date])),
    CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('dim-date'[Date]))
)
```

---

## 3. Measures

### General

| Measure | Table | Format | Description |
|---|---|---|---|
| `Total Sales Amount` | `_measures` | `#,##0.00` | — |
| `Order Count` | `_measures` | `#,##0` | — |
| `Avg Order Value` | `_measures` | `#,##0.00` | — |
| `Sales YTD` | `_measures` | `#,##0.00` | — |

**`Total Sales Amount`**
```dax
SUM('fact-sales'[amount])
```

**`Order Count`**
```dax
DISTINCTCOUNT('fact-sales'[order_id])
```

**`Avg Order Value`**
```dax
DIVIDE([Total Sales Amount], [Order Count], 0)
```

**`Sales YTD`**
```dax
TOTALYTD([Total Sales Amount], 'dim-date'[Date])
```

---

## 4. Relationships

| From Table | From Column | To Table | To Column | Cardinality |
|---|---|---|---|---|
| `Table1` | `Date` | `LocalDateTable_1235a396-8c1a-4354-82f9-f5dc91703c09` | `Date` | — |
| `Table1` | `Start of Week` | `LocalDateTable_87a55924-2729-4f83-89f5-0260ae9bd078` | `Date` | — |
| `Table1` | `End of Week` | `LocalDateTable_1a1b2bdd-c9f6-4dc5-b6d9-28538638be3a` | `Date` | — |
| `Table1` | `Last Day of Month` | `LocalDateTable_e663dc7d-baca-4273-8315-ce6c2fe4b2ac` | `Date` | — |
| `Table1` | `Last Quarter Day` | `LocalDateTable_61129bec-c6f6-4f3b-b99f-412a0e34948a` | `Date` | — |
| `Table2` | `Column1` | `Table1` | `Date` | — |
| `Table2` | `Column2` | `LocalDateTable_d251dd5f-12b8-4d75-ace6-35e887190b37` | `Date` | — |
| `Table2` | `Column3` | `LocalDateTable_0eaff71c-dbb4-416e-88a6-b353f8e8e519` | `Date` | — |
| `Table2` | `Column4` | `LocalDateTable_2dbf1ec4-7f1c-4ee5-88cd-2956680f6d61` | `Date` | — |
| `Table2` | `Column5` | `LocalDateTable_f016af82-450a-4cde-9149-0c70b51e9afe` | `Date` | — |
| `Table2` | `Column6` | `LocalDateTable_2f08567f-90b5-4fd0-a981-814ac9d9a273` | `Date` | — |
| `Table2` | `Column7` | `LocalDateTable_b20a67d5-65b4-482d-8e39-73c48b06cdf6` | `Date` | — |
| `Table2` | `Column8` | `LocalDateTable_a432e253-f22f-43c5-91c9-0dfe939cc1c8` | `Date` | — |
| `Table3` | `Column1` | `Table1` | `Date` | — |
| `Table3` | `Column2` | `LocalDateTable_02bcc64b-85d1-445f-bbf2-553a5c09407d` | `Date` | — |
| `Table4` | `Column1` | `Table1` | `Date` | — |
| `Table3` | `Column3` | `Table5` | `Key` | — |
| `Table4` | `Column2` | `Table5` | `Key` | — |

---

## 5. Security Roles

| Role | Table | Filter | Dynamic |
|---|---|---|---|
| `Regional Managers` | `fact-sales` | `[region] = "North"` | No |
| `Employees` | `dim-product` | `USERPRINCIPALNAME() = [email]` | Yes (USERPRINCIPALNAME) |
| `Legacy Users` | `dim-product` | `USERNAME() = [username]` | Yes (USERNAME) |
| `Area Supervisors` | `fact-sales` | `[region] = "South"` | No |
|  | `dim-product` | `[category] = "Hardware"` |  |
| `Administrators` | — | — | No |

---

## 6. M Parameters

| Parameter | Type | Value | Used By |
|---|---|---|---|
| `ServerName` | Text | `fake-server.database.windows.net` | `source-from-parameter` |
| `DatabaseName` | Text | `SalesDB` | `source-from-parameter` |

> *Only direct parameter references in connector calls are shown.
> Parameters used in conditional logic or computed expressions may not appear here.*

---

## ⚠ Unresolved Sources

The following sources could not be resolved statically.
Use tmdl-lens to provide a manual label for each.

| Expression | Reason |
|---|---|
| `source-dynamic` | Dynamic M - URL or query is built at runtime and cannot be statically resolved |

---

## 7. Model Statistics

| Category | Count | Items |
|---|---|---|
| Loaded Tables | 2 | `dim-product`, `fact-sales` |
| Calculated Tables | 1 | `dim-date` |
| Field Parameters | 1 | `param-metric-selector` |
| Measures-Only Tables | 1 | `_measures` |
| Calculation Groups | 1 | `cg-time-intelligence` |
| Not Loaded | 1 | `source-sql-staging` |
| Relationships | 18 | — |
| Measures | 4 | — |
| Calculated Columns | 0 | — |

---

*Generated by tmdl-lens · 29 March 2026*
