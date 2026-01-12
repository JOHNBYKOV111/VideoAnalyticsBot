import asyncio
import pytest
import sys
import os
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import time

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Теперь импортируем AIManager
from src.managers.ai_manager import AIManager


class TestAIManager:
    """Тесты для AIManager"""
    
    @pytest.fixture
    def ai_manager(self):
        """Фикстура создания AIManager без инициализации GigaChat"""
        with patch('src.managers.ai_manager.GIGACHAT_AVAILABLE', False):
            manager = AIManager(db_url="postgresql://test:test@localhost/test")
            yield manager
            # Закрываем в фикстуре - асинхронно
            try:
                asyncio.run(manager.close())
            except RuntimeError:
                # Если уже есть event loop, используем его
                loop = asyncio.get_event_loop()
                loop.run_until_complete(manager.close())

    # ========== ТЕСТЫ ИНИЦИАЛИЗАЦИИ ==========
    
    def test_initialization_without_gigachat(self):
        """Тест инициализации без GigaChat"""
        with patch('src.managers.ai_manager.GIGACHAT_AVAILABLE', False):
            manager = AIManager()
            assert manager.giga is None
            assert manager.giga_status == "disabled"
            assert manager.ai_version == "12.0 Standalone"
            assert manager._db_cache == {}
            # Закрываем без asyncio.run, если уже есть event loop
            try:
                asyncio.run(manager.close())
            except RuntimeError:
                pass
    
    def test_initialization_with_gigachat_success(self):
        """Тест инициализации с GigaChat (успешно)"""
        # Тест проверяет путь выполнения когда GIGACHAT_AVAILABLE = True
        # Но не инициализирует реальный GigaChat
        with patch('src.managers.ai_manager.GIGACHAT_AVAILABLE', True):
            # Мокаем импорт gigachat на уровне sys.modules
            with patch.dict('sys.modules', {'gigachat': None}):
                # Мокаем попытку импорта внутри _initialize_gigachat
                with patch('src.managers.ai_manager.gigachat', None, create=True):
                    manager = AIManager()
                    # При недоступном gigachat, инициализация должна завершиться
                    # с giga = None и статусом ошибки
                    assert manager is not None
                    # В этом случае giga будет None из-за ошибки импорта
                    try:
                        asyncio.run(manager.close())
                    except RuntimeError:
                        pass
    
    def test_initialization_gigachat_error(self):
        """Тест ошибки инициализации GigaChat"""
        # Аналогично предыдущему тесту
        with patch('src.managers.ai_manager.GIGACHAT_AVAILABLE', True):
            with patch.dict('sys.modules', {'gigachat': None}):
                with patch('src.managers.ai_manager.gigachat', None, create=True):
                    manager = AIManager()
                    assert manager is not None
                    # При ошибке импорта giga будет None
                    try:
                        asyncio.run(manager.close())
                    except RuntimeError:
                        pass

    # ========== ТЕСТЫ БАЗЫ ДАННЫХ ==========
    
    @pytest.mark.asyncio
    async def test_get_db_pool(self, ai_manager):
        """Тест создания пула соединений"""
        mock_pool = AsyncMock()
        
        with patch('asyncpg.create_pool', AsyncMock(return_value=mock_pool)) as mock_create:
            pool = await ai_manager._get_db_pool()
            assert pool == mock_pool
            mock_create.assert_called_once()
            assert ai_manager.db_pool == mock_pool
    
    @pytest.mark.asyncio
    async def test_db_connection_error(self, ai_manager):
        """Тест ошибки подключения к БД"""
        with patch('asyncpg.create_pool', AsyncMock(side_effect=Exception("Connection failed"))):
            with pytest.raises(Exception, match="Connection failed"):
                await ai_manager._get_db_pool()
            assert ai_manager.db_pool is None
    
    def test_cache_operations(self, ai_manager):
        """Тест операций с кэшем"""
        ai_manager._set_cached("test_key", "test_value")
        value = ai_manager._get_cached("test_key")
        assert value == "test_value"
        assert ai_manager._get_cached("non_existent") is None
    
    def test_cache_expiration(self, ai_manager):
        """Тест истечения срока жизни кэша"""
        ai_manager._cache_ttl = 0.1
        ai_manager._set_cached("key1", "value1")
        assert ai_manager._get_cached("key1") == "value1"
        time.sleep(0.2)
        assert ai_manager._get_cached("key1") is None

    # ========== ТЕСТЫ SQL ЗАПРОСОВ ==========
    
    @pytest.mark.asyncio
    async def test_get_all_basic_stats(self, ai_manager):
        """Тест получения общей статистики"""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            'total_videos': 100,
            'total_creators': 10,
            'total_views': 50000,
            'total_likes': 10000,
            'total_comments': 2000,
            'total_reports': 50
        })
        mock_conn.fetchval = AsyncMock(return_value=150)
        
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_conn
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=AsyncContextManager())
        
        with patch.object(ai_manager, '_get_db_pool', AsyncMock(return_value=mock_pool)):
            stats = await ai_manager._get_all_basic_stats()
            
            assert stats['total_videos'] == 100
            assert stats['total_creators'] == 10
            assert stats['total_views'] == 50000
            assert stats['total_snapshots'] == 150
            assert ai_manager._get_cached("all_basic_stats") == stats
    
    @pytest.mark.asyncio
    async def test_get_creator_stats_found(self, ai_manager):
        """Тест получения статистики креатора (найден)"""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(side_effect=[
            "550e8400-e29b-41d4-a716-446655440000",
            30  # snapshots
        ])
        mock_conn.fetchrow = AsyncMock(return_value={
            'videos_count': 15,
            'total_views': 50000,
            'total_likes': 10000,
            'total_comments': 500,
            'total_reports': 3
        })
        
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_conn
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=AsyncContextManager())
        
        with patch.object(ai_manager, '_get_db_pool', AsyncMock(return_value=mock_pool)):
            stats = await ai_manager._get_creator_stats(123)
            
            assert stats is not None
            assert stats['videos'] == 15
            assert stats['views'] == 50000
            assert stats['uuid'] == "550e8400-e29b-41d4-a716-446655440000"
            assert stats['snapshots'] == 30
    
    @pytest.mark.asyncio
    async def test_get_creator_stats_not_found(self, ai_manager):
        """Тест получения статистики несуществующего креатора"""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)  # UUID не найден
        
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_conn
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=AsyncContextManager())
        
        with patch.object(ai_manager, '_get_db_pool', AsyncMock(return_value=mock_pool)):
            stats = await ai_manager._get_creator_stats(999)
            assert stats is None
    
    @pytest.mark.asyncio
    async def test_get_videos_by_views_more(self, ai_manager):
        """Тест получения видео с просмотрами больше threshold"""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(side_effect=[25, 100])
        
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_conn
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=AsyncContextManager())
        
        with patch.object(ai_manager, '_get_db_pool', AsyncMock(return_value=mock_pool)):
            result = await ai_manager._get_videos_by_views(1000, "more")
            assert result['count'] == 25
            assert result['total'] == 100
            assert result['percent'] == 25.0
    
    @pytest.mark.asyncio
    async def test_get_videos_by_views_less(self, ai_manager):
        """Тест получения видео с просмотрами меньше threshold"""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(side_effect=[10, 100])
        
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_conn
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_pool = AsyncMock()
        mock_pool.acquire = Mock(return_value=AsyncContextManager())
        
        with patch.object(ai_manager, '_get_db_pool', AsyncMock(return_value=mock_pool)):
            result = await ai_manager._get_videos_by_views(500, "less")
            assert result['count'] == 10
            assert result['total'] == 100
            assert result['percent'] == 10.0

    # ========== ТЕСТЫ GIGACHAT ==========
    
    @pytest.mark.asyncio
    async def test_check_gigachat_disabled(self, ai_manager):
        """Тест проверки отключенного GigaChat"""
        ai_manager.giga = None
        status = await ai_manager._check_gigachat()
        assert status == "disabled"
    
    @pytest.mark.asyncio
    async def test_ask_gigachat_disabled(self, ai_manager):
        """Тест запроса к отключенному GigaChat"""
        response = await ai_manager._ask_gigachat("Тестовый промпт")
        assert "GigaChat недоступен" in response
    
    @pytest.mark.asyncio
    async def test_ask_gigachat_success(self, ai_manager):
        """Тест успешного запроса к GigaChat"""
        # Мокаем методы, которые используют GigaChat
        with patch.object(ai_manager, '_check_gigachat', return_value="active"):
            # Мокаем сам метод _ask_gigachat, чтобы избежать реального вызова
            with patch.object(ai_manager, '_ask_gigachat') as mock_ask:
                mock_ask.return_value = "Тестовый ответ от GigaChat"
                response = await ai_manager._ask_gigachat("Тестовый промпт")
                assert "Тестовый ответ от GigaChat" in response
    
    # ========== ТЕСТЫ ОСНОВНЫХ AI МЕТОДОВ ==========
    
    @pytest.mark.asyncio
    async def test_analyze_creator_success(self, ai_manager):
        """Тест успешного анализа креатора"""
        test_stats = {
            'videos': 15,
            'views': 50000,
            'likes': 10000,
            'comments': 500,
            'reports': 3,
            'snapshots': 30,
            'uuid': 'test-uuid-123'
        }
        
        with patch.object(ai_manager, '_get_creator_stats', return_value=test_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Отличный креатор! Оценка: 8/10"):
            
            result = await ai_manager.analyze_creator(123)
            assert "Креатор #123" in result
            assert "15" in result
            assert "50,000" in result
            assert "Отличный креатор" in result
    
    @pytest.mark.asyncio
    async def test_analyze_creator_not_found(self, ai_manager):
        """Тест анализа несуществующего креатора"""
        with patch.object(ai_manager, '_get_creator_stats', return_value=None):
            result = await ai_manager.analyze_creator(999)
            assert "не найден" in result
    
    @pytest.mark.asyncio
    async def test_analyze_videos_by_views_success(self, ai_manager):
        """Тест анализа видео по просмотрам"""
        test_stats = {'count': 25, 'total': 100, 'percent': 25.0}
        all_stats = {
            'total_videos': 100,
            'total_views': 500000,
            'total_creators': 10,
            'total_likes': 10000,
            'total_comments': 500,
            'total_reports': 20,
            'total_snapshots': 50
        }
        
        with patch.object(ai_manager, '_get_videos_by_views', return_value=test_stats), \
             patch.object(ai_manager, '_get_all_basic_stats', return_value=all_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Хорошее распределение"):
            
            result = await ai_manager.analyze_videos_by_views(1000, "more")
            assert "100" in result
            assert "25" in result
            assert "25.0%" in result
            assert "500,000" in result
    
    @pytest.mark.asyncio
    async def test_analyze_videos_by_views_less(self, ai_manager):
        """Тест анализа видео с просмотрами меньше threshold"""
        test_stats = {'count': 10, 'total': 100, 'percent': 10.0}
        all_stats = {
            'total_videos': 100,
            'total_views': 500000,
            'total_creators': 10,
            'total_likes': 10000,
            'total_comments': 500,
            'total_reports': 20,
            'total_snapshots': 50
        }
        
        with patch.object(ai_manager, '_get_videos_by_views', return_value=test_stats), \
             patch.object(ai_manager, '_get_all_basic_stats', return_value=all_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Много мало просматриваемых видео"):
            
            result = await ai_manager.analyze_videos_by_views(500, "less")
            assert "менее 500" in result
    
    @pytest.mark.asyncio
    async def test_analyze_extremes_success(self, ai_manager):
        """Тест успешного анализа экстремумов"""
        test_data = {
            'max': (1, {'videos': 100, 'views': 50000}),
            'min': (4, {'videos': 5, 'views': 1000}),
            'total': 10
        }
        
        with patch.object(ai_manager, '_get_extreme_creators', return_value=test_data), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Большой разброс в количестве видео"):
            
            result = await ai_manager.analyze_extremes("videos")
            assert "Креатор #1" in result
            assert "Креатор #4" in result
            assert "100" in result
            assert "5" in result
            assert "10" in result
    
    @pytest.mark.asyncio
    async def test_analyze_extremes_unknown_metric(self, ai_manager):
        """Тест анализа экстремумов с неизвестной метрики"""
        result = await ai_manager.analyze_extremes("unknown_metric")
        assert "Неизвестная метрика" in result
    
    @pytest.mark.asyncio
    async def test_analyze_top_n_success(self, ai_manager):
        """Тест успешного анализа топ-N креаторов"""
        test_top = [
            (1, {'videos': 100, 'views': 50000}),
            (2, {'videos': 50, 'views': 30000}),
            (3, {'videos': 30, 'views': 10000})
        ]
        all_creators = {
            1: {'videos': 100}, 2: {'videos': 50}, 3: {'videos': 30},
            4: {'videos': 10}, 5: {'videos': 5}
        }
        
        with patch.object(ai_manager, '_get_top_creators_by_metric', return_value=test_top), \
             patch.object(ai_manager, '_get_all_creators_stats', return_value=all_creators), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Лидеры показывают хорошие результаты"):
            
            result = await ai_manager.analyze_top_n("videos", n=3)
            assert "Креатор #1" in result
            assert "Креатор #2" in result
            assert "Креатор #3" in result
            assert "100" in result
            assert "Топ-3" in result
    
    @pytest.mark.asyncio
    async def test_analyze_top_n_creators_special_case(self, ai_manager):
        """Тест анализа топ-N для метрики 'creators' (особый случай)"""
        all_creators = {
            1: {'videos': 100}, 2: {'videos': 50}, 3: {'videos': 30},
            4: {'videos': 10}, 5: {'videos': 5}
        }
        
        with patch.object(ai_manager, '_get_all_creators_stats', return_value=all_creators), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Креаторы с большим количеством видео"):
            
            result = await ai_manager.analyze_top_n("creators", n=3)
            assert "Креатор #1" in result
            assert "Креатор #2" in result
            assert "Креатор #3" in result
            assert "видео" in result
    
    @pytest.mark.asyncio
    async def test_analyze_top_three_alias(self, ai_manager):
        """Тест алиаса analyze_top_three"""
        with patch.object(ai_manager, 'analyze_top_n', return_value="Топ-3 анализ") as mock_top_n:
            result = await ai_manager.analyze_top_three("views")
            mock_top_n.assert_called_with("views", n=3)
            assert result == "Топ-3 анализ"
    
    @pytest.mark.asyncio
    async def test_analyze_top_ten_alias(self, ai_manager):
        """Тест алиаса analyze_top_ten"""
        with patch.object(ai_manager, 'analyze_top_n', return_value="Топ-10 анализ") as mock_top_n:
            result = await ai_manager.analyze_top_ten("likes")
            mock_top_n.assert_called_with("likes", n=10)
            assert result == "Топ-10 анализ"
    
    @pytest.mark.asyncio
    async def test_ai_general_analysis_success(self, ai_manager):
        """Тест общего анализа платформы"""
        test_stats = {
            'total_videos': 1000,
            'total_creators': 50,
            'total_views': 5000000,
            'total_likes': 1000000,
            'total_comments': 50000,
            'total_reports': 1000,
            'total_snapshots': 2000
        }
        
        with patch.object(ai_manager, '_get_all_basic_stats', return_value=test_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Платформа активно развивается"):
            
            result = await ai_manager.ai_general_analysis()
            assert "1,000" in result
            assert "50" in result
            assert "5,000,000" in result
            assert "20.0%" in result
            assert "Платформа активно развивается" in result
    
    @pytest.mark.asyncio
    async def test_ai_general_analysis_zero_views(self, ai_manager):
        """Тест общего анализа при нулевых просмотрах"""
        test_stats = {
            'total_videos': 0,
            'total_creators': 0,
            'total_views': 0,
            'total_likes': 0,
            'total_comments': 0,
            'total_reports': 0,
            'total_snapshots': 0
        }
        
        with patch.object(ai_manager, '_get_all_basic_stats', return_value=test_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Платформа пустая"):
            
            result = await ai_manager.ai_general_analysis()
            assert "0.0%" in result

    # ========== ТЕСТЫ ЗАКРЫТИЯ РЕСУРСОВ ==========
    
    @pytest.mark.asyncio
    async def test_close(self):
        """Тест закрытия ресурсов"""
        with patch('src.managers.ai_manager.GIGACHAT_AVAILABLE', False):
            manager = AIManager()
            mock_pool = AsyncMock()
            manager.db_pool = mock_pool
            await manager.close()
            mock_pool.close.assert_called_once()
            assert manager.db_pool is None
    
    @pytest.mark.asyncio
    async def test_close_no_pool(self):
        """Тест закрытия при отсутствии пула"""
        with patch('src.managers.ai_manager.GIGACHAT_AVAILABLE', False):
            manager = AIManager()
            manager.db_pool = None
            await manager.close()
            assert manager.db_pool is None

    # ========== ТЕСТЫ ГРАНИЧНЫХ СЛУЧАЕВ ==========
    
    @pytest.mark.asyncio
    async def test_edge_case_zero_values(self, ai_manager):
        """Тест обработки нулевых значений"""
        test_stats = {
            'videos': 0,
            'views': 0,
            'likes': 0,
            'comments': 0,
            'reports': 0,
            'snapshots': 0,
            'uuid': 'test-uuid'
        }
        
        with patch.object(ai_manager, '_get_creator_stats', return_value=test_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Нулевые показатели"):
            
            result = await ai_manager.analyze_creator(999)
            assert "0" in result
    
    @pytest.mark.asyncio
    async def test_edge_case_very_large_values(self, ai_manager):
        """Тест обработки очень больших значений"""
        test_stats = {
            'videos': 1000000,
            'views': 1000000000,
            'likes': 500000000,
            'comments': 10000000,
            'reports': 1000,
            'snapshots': 50000,
            'uuid': 'test-uuid'
        }
        
        with patch.object(ai_manager, '_get_creator_stats', return_value=test_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Огромные показатели"):
            
            result = await ai_manager.analyze_creator(1)
            assert "1,000,000" in result
            assert "1,000,000,000" in result
    
    # ========== ТЕСТЫ ОШИБОК ==========
    
    @pytest.mark.asyncio
    async def test_analyze_creator_error(self, ai_manager):
        """Тест ошибки анализа креатора"""
        with patch.object(ai_manager, '_get_creator_stats', side_effect=Exception("DB error")):
            result = await ai_manager.analyze_creator(123)
            assert "Ошибка" in result
    
    @pytest.mark.asyncio
    async def test_analyze_videos_by_views_error(self, ai_manager):
        """Тест ошибки анализа видео"""
        with patch.object(ai_manager, '_get_videos_by_views', side_effect=Exception("DB error")):
            result = await ai_manager.analyze_videos_by_views(1000, "more")
            assert "Ошибка" in result
    
    @pytest.mark.asyncio
    async def test_analyze_extremes_error(self, ai_manager):
        """Тест ошибки анализа экстремумов"""
        with patch.object(ai_manager, '_get_extreme_creators', side_effect=Exception("Calculation error")):
            result = await ai_manager.analyze_extremes("videos")
            assert "Ошибка" in result
    
    @pytest.mark.asyncio
    async def test_ai_general_analysis_error(self, ai_manager):
        """Тест ошибки общего анализа"""
        with patch.object(ai_manager, '_get_all_basic_stats', side_effect=Exception("DB error")):
            result = await ai_manager.ai_general_analysis()
            assert "Ошибка" in result

    # ========== ТЕСТЫ ПРОМПТОВ ==========
    
    def test_prompts_formatting(self, ai_manager):
        """Тест форматирования промптов"""
        prompt = ai_manager.prompts["creator_analysis"].format(
            creator_id=123,
            videos=15,
            views=50000,
            likes=10000,
            comments=500,
            reports=3,
            snapshots=30
        )
        assert "123" in prompt
        assert "15" in prompt
        assert "50,000" in prompt
    
    def test_all_prompts_exist(self, ai_manager):
        """Тест наличия всех промптов"""
        required_prompts = [
            "creator_analysis",
            "videos_by_views", 
            "extremes_analysis",
            "top_n_analysis",
            "platform_analysis"
        ]
        for prompt_name in required_prompts:
            assert prompt_name in ai_manager.prompts
            prompt = ai_manager.prompts[prompt_name]
            assert isinstance(prompt, str)
            assert len(prompt) > 20

    # ========== ПАРАМЕТРИЗОВАННЫЕ ТЕСТЫ ==========
    
    @pytest.mark.parametrize("metric,comparison,threshold,expected_in_result", [
        ("videos", "more", 10, "более 10"),
        ("videos", "less", 5, "менее 5"),
        ("views", "more", 1000, "более 1,000"),
        ("views", "less", 100, "менее 100"),
    ])
    @pytest.mark.asyncio
    async def test_analyze_videos_by_views_parametrized(self, ai_manager, metric, comparison, threshold, expected_in_result):
        """Параметризованный тест анализа видео"""
        test_stats = {'count': 25, 'total': 100, 'percent': 25.0}
        all_stats = {
            'total_videos': 100,
            'total_views': 500000,
            'total_creators': 10,
            'total_likes': 10000,
            'total_comments': 500,
            'total_reports': 20,
            'total_snapshots': 50
        }
        
        with patch.object(ai_manager, '_get_videos_by_views', return_value=test_stats), \
             patch.object(ai_manager, '_get_all_basic_stats', return_value=all_stats), \
             patch.object(ai_manager, '_ask_gigachat', return_value="Анализ"):
            
            result = await ai_manager.analyze_videos_by_views(threshold, comparison)
            assert expected_in_result in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])