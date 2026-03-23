-- phpMyAdmin SQL Dump
-- version 5.2.2
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1:3306
-- Tempo de geração: 21/03/2026 às 18:52
-- Versão do servidor: 11.8.3-MariaDB-log
-- Versão do PHP: 7.2.34

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Banco de dados: `u234303836_maskja`
--

-- --------------------------------------------------------

--
-- Estrutura para tabela `apis`
--

CREATE TABLE `apis` (
  `id` varchar(255) NOT NULL,
  `provider_name` varchar(255) NOT NULL,
  `endpoint` text NOT NULL,
  `agent_code` varchar(255) NOT NULL,
  `agent_token` text NOT NULL,
  `agent_secret` text NOT NULL,
  `status` varchar(50) NOT NULL DEFAULT 'active',
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `identifier_type` varchar(50) NOT NULL DEFAULT 'id',
  `rtp_agent` int(11) NOT NULL DEFAULT 95,
  `rtp_influencer` int(11) NOT NULL DEFAULT 120
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

--
-- Despejando dados para a tabela `apis`
--

INSERT INTO `apis` (`id`, `provider_name`, `endpoint`, `agent_code`, `agent_token`, `agent_secret`, `status`, `created_at`, `updated_at`, `identifier_type`, `rtp_agent`, `rtp_influencer`) VALUES
('4150838f-6011-4564-9ec7-8891d1e62394', 'BauPG', 'https://api.baupg.com/', 'jaialves', '4944655e02009d5cf4548d65d913a590', '754af06fb6e2c50400360e10266f185c', 'active', '2026-03-19 17:17:25', '2026-03-19 17:17:25', 'id', 95, 120);

-- --------------------------------------------------------

--
-- Estrutura para tabela `api_config`
--

CREATE TABLE `api_config` (
  `id` varchar(255) NOT NULL,
  `url` text NOT NULL,
  `agent_code` varchar(255) NOT NULL,
  `agent_token` text NOT NULL,
  `agent_secret` text NOT NULL,
  `active` int(11) NOT NULL DEFAULT 1,
  `rtp_agent` int(11) NOT NULL DEFAULT 95,
  `rtp_influencer` int(11) NOT NULL DEFAULT 120,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura para tabela `games`
--

CREATE TABLE `games` (
  `id` varchar(255) NOT NULL,
  `game_name` varchar(255) NOT NULL,
  `game_code` varchar(255) NOT NULL,
  `provider` varchar(255) NOT NULL,
  `distribution` varchar(255) NOT NULL,
  `status` varchar(50) NOT NULL DEFAULT '1',
  `popular` varchar(50) NOT NULL DEFAULT '0',
  `banner` text DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `slug` varchar(255) DEFAULT NULL,
  `api_id` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

--
-- Despejando dados para a tabela `games`
--

INSERT INTO `games` (`id`, `game_name`, `game_code`, `provider`, `distribution`, `status`, `popular`, `banner`, `created_at`, `updated_at`, `slug`, `api_id`) VALUES
('126', 'Fortune Rabbit', 'fortune-rabbit', 'PG Soft', 'KSeven', '1', '1', 'https://static.pga-nmga5.com/m/games/126/banner.png', '2026-03-19 17:14:28', '2026-03-19 17:17:59', 'fortune-rabbit', '4150838f-6011-4564-9ec7-8891d1e62394'),
('1543462', 'Fortune Mouse', 'fortune-mouse', 'PG Soft', 'KSeven', '1', '1', 'https://static.pga-nmga5.com/m/games/1543462/banner.png', '2026-03-19 17:14:28', '2026-03-19 17:18:06', 'fortune-mouse', '4150838f-6011-4564-9ec7-8891d1e62394'),
('63', 'Fortune Tiger', 'fortune-tiger', 'PG Soft', 'KSeven', '1', '1', 'https://static.pga-nmga5.com/m/games/63/banner.png', '2026-03-19 17:14:28', '2026-03-19 17:17:40', 'fortune-tiger', '4150838f-6011-4564-9ec7-8891d1e62394'),
('98', 'Fortune Ox', 'fortune-ox', 'PG Soft', 'KSeven', '1', '1', 'https://static.pga-nmga5.com/m/games/98/banner.png', '2026-03-19 17:14:28', '2026-03-19 17:17:52', 'fortune-ox', '4150838f-6011-4564-9ec7-8891d1e62394');

-- --------------------------------------------------------

--
-- Estrutura para tabela `game_sessions`
--

CREATE TABLE `game_sessions` (
  `id` varchar(255) NOT NULL,
  `user_id` varchar(255) NOT NULL,
  `game_id` varchar(255) NOT NULL,
  `api_id` varchar(255) NOT NULL,
  `operator_token` varchar(255) NOT NULL,
  `launch_url` text DEFAULT NULL,
  `status` varchar(50) NOT NULL DEFAULT 'pending',
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `expires_at` datetime NOT NULL,
  `ticket` varchar(255) DEFAULT NULL,
  `initial_balance` int(11) DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estrutura para tabela `logs`
--

CREATE TABLE `logs` (
  `id` varchar(255) NOT NULL,
  `type` varchar(50) NOT NULL,
  `message` text NOT NULL,
  `details` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`details`)),
  `timestamp` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- --------------------------------------------------------

--
-- Estrutura para tabela `profiles`
--

CREATE TABLE `profiles` (
  `id` varchar(255) NOT NULL,
  `username` varchar(255) NOT NULL,
  `balance` int(11) NOT NULL DEFAULT 0,
  `currency` varchar(10) NOT NULL DEFAULT 'R$',
  `status` varchar(50) NOT NULL DEFAULT 'active',
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `is_influencer` int(11) NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

--
-- Despejando dados para a tabela `profiles`
--

INSERT INTO `profiles` (`id`, `username`, `balance`, `currency`, `status`, `created_at`, `updated_at`, `is_influencer`) VALUES
('18b5d45a-79bd-4356-bf48-eb9fc8eaa2af', 'Player_96692', 5000, 'R$', 'active', '2026-03-20 18:29:32', '2026-03-20 18:29:32', 0),
('5212ad9b-4a70-4841-a279-2fd4bb69d50d', '', 1000, 'R$', 'active', '2026-03-20 17:35:14', '2026-03-20 17:35:14', 0),
('98f420b3-61e5-4037-b889-fa9537ac1cd7', 'Player_12867', 5000, 'R$', 'active', '2026-03-20 18:31:10', '2026-03-20 18:31:10', 0),
('9b078d51-49e7-4888-b5b0-d90c662d36b4', 'Player_29060', 5000, 'R$', 'active', '2026-03-20 18:27:08', '2026-03-20 18:27:08', 0),
('9e225ea5-51bc-43ff-bfea-daca4f552740', 'Player_52613', 4541, 'R$', 'active', '2026-03-20 18:01:31', '2026-03-20 18:01:31', 0),
('bcceb668-3ada-499c-a4a0-103238288b35', 'Player_60447', 5000, 'R$', 'active', '2026-03-20 18:23:05', '2026-03-20 18:23:05', 0),
('c4dd43cc-fe58-4370-931d-142fadc2e436', 'Player_10498', 5000, 'R$', 'active', '2026-03-20 18:35:34', '2026-03-21 18:27:32', 0),
('cb6aee95-2366-4719-a25a-19fbe5598aff', 'Player_63558', 4541, 'R$', 'active', '2026-03-20 18:00:36', '2026-03-20 18:00:36', 0),
('demo-profile-1', 'Jogador_Teste', 10000, 'R$', 'active', '2026-03-19 17:14:29', '2026-03-19 20:33:51', 0),
('demo-profile-2', 'Lucas', 5000, 'R$', 'active', '2026-03-19 17:14:29', '2026-03-19 20:33:51', 1);

-- --------------------------------------------------------

--
-- Estrutura para tabela `system_settings`
--

CREATE TABLE `system_settings` (
  `id` varchar(255) NOT NULL,
  `key` varchar(255) NOT NULL,
  `value` text NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

--
-- Despejando dados para a tabela `system_settings`
--

INSERT INTO `system_settings` (`id`, `key`, `value`, `updated_at`) VALUES
('1', 'registration_enabled', 'true', '2026-03-19 17:14:28'),
('2', 'site_name', 'SimPG Browser', '2026-03-19 17:14:28'),
('3', 'maintenance_mode', 'false', '2026-03-19 17:14:28'),
('f5eaea9a-1071-4c7e-aa64-037e07253eef', '', '', '2026-03-21 18:21:14');

-- --------------------------------------------------------

--
-- Estrutura para tabela `users`
--

CREATE TABLE `users` (
  `id` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `password` text NOT NULL,
  `display_name` text NOT NULL,
  `role` varchar(50) NOT NULL DEFAULT 'user',
  `status` varchar(50) NOT NULL DEFAULT 'active',
  `photo_url` text DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

--
-- Despejando dados para a tabela `users`
--

INSERT INTO `users` (`id`, `email`, `password`, `display_name`, `role`, `status`, `photo_url`, `created_at`) VALUES
('67913b8a-9333-42e3-8d0f-b3f051c35b0b', 'admin@gmail.com', '$2b$10$Q1Mm8SaXGOaPlxpL7AAXGOQW/2TpEpyI3uzV93i5YAYEydqTNi7eW', 'Administrador', 'admin', 'active', 'https://ui-avatars.com/api/?name=Administrador&background=random', '2026-03-19 18:25:55'),
('96d701bd-ebe1-4102-99e9-d7af56b96ba2', 'felipe@gmail.com', '$2b$10$Q1Mm8SaXGOaPlxpL7AAXGOQW/2TpEpyI3uzV93i5YAYEydqTNi7eW', 'Felipe', 'admin', 'active', 'https://ui-avatars.com/api/?name=Felipe&background=random', '2026-03-21 17:39:47'),
('f1c12c47-7c9e-468f-bc20-32891eb3bef4', 'user@gmail.com', '$2b$10$Q1Mm8SaXGOaPlxpL7AAXGOQW/2TpEpyI3uzV93i5YAYEydqTNi7eW', 'User', 'user', 'active', 'https://ui-avatars.com/api/?name=User&background=random', '2026-03-19 17:16:28');

--
-- Índices para tabelas despejadas
--

--
-- Índices de tabela `apis`
--
ALTER TABLE `apis`
  ADD PRIMARY KEY (`id`);

--
-- Índices de tabela `api_config`
--
ALTER TABLE `api_config`
  ADD PRIMARY KEY (`id`);

--
-- Índices de tabela `games`
--
ALTER TABLE `games`
  ADD PRIMARY KEY (`id`);

--
-- Índices de tabela `game_sessions`
--
ALTER TABLE `game_sessions`
  ADD PRIMARY KEY (`id`);

--
-- Índices de tabela `logs`
--
ALTER TABLE `logs`
  ADD PRIMARY KEY (`id`);

--
-- Índices de tabela `profiles`
--
ALTER TABLE `profiles`
  ADD PRIMARY KEY (`id`);

--
-- Índices de tabela `system_settings`
--
ALTER TABLE `system_settings`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `key` (`key`);

--
-- Índices de tabela `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `email` (`email`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
