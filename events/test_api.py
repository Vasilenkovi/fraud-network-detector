import pytest
from django.test import Client

@pytest.fixture
def api_client():
    return Client()

# 1. ТЕСТЫ ДЛЯ ОЧЕРЕДИ (GET /api/alerts/)

@pytest.mark.django_db
def test_get_alerts_empty_list(api_client):
    """Проверяем, что пустая база возвращает пустой список (200 OK)"""
    response = api_client.get('/api/alerts/')
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 0

# 2. ТЕСТЫ ДЛЯ КАРТОЧКИ (GET /api/alerts/{id}/)

@pytest.mark.django_db
def test_get_alert_details_not_found(api_client):
    """Проверяем, что при запросе несуществующего ID возвращается 404"""
    response = api_client.get('/api/alerts/non-existent-id-999/')
    assert response.status_code == 404


# 3. ТЕСТЫ ДЛЯ ПРИНЯТИЯ РЕШЕНИЯ (POST /api/alerts/{id}/decision/)

@pytest.mark.django_db
def test_post_decision_reject_without_comment(api_client):
    """
    Проверяем валидацию (Требование ТИ-42): 
    Если отклоняем группу, но не пишем комментарий — сервер должен вернуть 400.
    """
    payload = {
        "status": "rejected"
        # comment намеренно не передаем
    }
    response = api_client.post('/api/alerts/1/decision/', data=payload, format='json')
    
    assert response.status_code == 400
    # Проверяем, что в ответе есть поле 'comment' (указание на ошибку)
    assert 'comment' in response.json()

@pytest.mark.django_db
def test_post_decision_reject_with_comment(api_client):
    """Проверяем, что с комментарием запрос проходит валидацию (возвращает 200 или 404, если группы нет)"""
    payload = {
        "status": "rejected",
        "comment": "Это ложное срабатывание, клиенты — семья"
    }
    response = api_client.post('/api/alerts/1/decision/', data=payload, format='json')
    
    # Если алерта нет, вернется 404. Если есть — 200. Главное, что не 400.
    assert response.status_code in [200, 404]

# 4. ТЕСТЫ ДЛЯ REPLAY (POST /api/replay/)

@pytest.mark.django_db
def test_post_replay_success(api_client):
    """Проверяем запуск повторной обработки (должен вернуть 202 Accepted)"""
    payload = {
        "start_time": "2026-01-01T10:00:00Z",
        "end_time": "2026-01-02T12:00:00Z"
    }
    response = api_client.post('/api/replay/', data=payload, format='json')
    
    assert response.status_code == 202

@pytest.mark.django_db
def test_post_replay_validation_error(api_client):
    """Проверяем, что если передать кривые даты, сервер вернет 400 Bad Request"""
    payload = {
        "start_time": "invalid-date",
        "end_time": "invalid-date"
    }
    response = api_client.post('/api/replay/', data=payload, format='json')
    
    assert response.status_code == 400