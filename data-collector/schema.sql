--
-- PostgreSQL database dump
--

\restrict DUr0h940rbkMh7WWGkiEMs4P5z49b48RuJgcW08O3pCOZnGXmal7MF1hh2sAWnU

-- Dumped from database version 18.6 (Ubuntu 18.6-0ubuntu0.26.04.1)
-- Dumped by pg_dump version 18.6 (Ubuntu 18.6-0ubuntu0.26.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: futures_orderbook_depth_5; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.futures_orderbook_depth_5 (
    "timestamp" bigint,
    best1_bid double precision,
    best1_bid_qty double precision,
    best1_ask double precision,
    best1_ask_qty double precision,
    best2_bid double precision,
    best2_bid_qty double precision,
    best2_ask double precision,
    best2_ask_qty double precision,
    best3_bid double precision,
    best3_bid_qty double precision,
    best3_ask double precision,
    best3_ask_qty double precision,
    best4_bid double precision,
    best4_bid_qty double precision,
    best4_ask double precision,
    best4_ask_qty double precision,
    best5_bid double precision,
    best5_bid_qty double precision,
    best5_ask double precision,
    best5_ask_qty double precision,
    mid double precision,
    spread double precision
);


--
-- Name: idx_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_timestamp ON public.futures_orderbook_depth_5 USING btree ("timestamp");


--
-- PostgreSQL database dump complete
--

\unrestrict DUr0h940rbkMh7WWGkiEMs4P5z49b48RuJgcW08O3pCOZnGXmal7MF1hh2sAWnU

