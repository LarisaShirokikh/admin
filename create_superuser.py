#!/usr/bin/env python3
# create_superuser.py
"""
Асинхронный скрипт для создания первого суперадмина
"""

import sys
import os
import getpass
import asyncio

# Добавляем текущую директорию в путь
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

async def create_superuser():
    """Создание суперадмина"""
    print("=== Создание суперадмина ===")
    
    try:
        print("1. Импортируем модули...")
        from app.deps import get_db
        from app.crud.admin import admin_user
        from app.schemas.admin import AdminUserCreate
        print("✅ CRUD и схемы импортированы")
        
        print("2. Подключаемся к БД...")
        # Используем вашу функцию get_db()
        db_generator = get_db()
        db = await db_generator.__anext__()
        
        try:
            print("✅ Подключение к БД успешно")
            
            print("3. Проверяем существующих админов...")
            existing_admins = await admin_user.get_multi(db, limit=5)
            if existing_admins:
                print(f"⚠️  Найдено {len(existing_admins)} админов:")
                for admin in existing_admins:
                    role = "суперадмин" if admin.is_superuser else "админ"
                    print(f"   - {admin.username} ({role})")
                
                confirm = input("Продолжить создание нового суперадмина? (y/N): ")
                if confirm.lower() != 'y':
                    print("Отменено")
                    return
            
            print("\n4. Вводим данные для суперадмина...")
            
            # Ввод username
            while True:
                username = input("Username: ").strip()
                if len(username) < 3:
                    print("❌ Username должен быть минимум 3 символа")
                    continue
                
                existing_user = await admin_user.get_by_username(db, username)
                if existing_user:
                    print(f"❌ Username '{username}' уже существует")
                    continue
                break
            
            # Ввод email
            while True:
                email = input("Email: ").strip()
                if '@' not in email or '.' not in email:
                    print("❌ Введите корректный email")
                    continue
                
                existing_email = await admin_user.get_by_email(db, email)
                if existing_email:
                    print(f"❌ Email '{email}' уже используется")
                    continue
                break
            
            # Ввод пароля
            while True:
                password = getpass.getpass("Пароль: ")
                if len(password) < 6:
                    print("❌ Пароль должен быть минимум 6 символов")
                    continue
                confirm_password = getpass.getpass("Подтвердите пароль: ")
                if password != confirm_password:
                    print("❌ Пароли не совпадают")
                    continue
                break
            
            print("5. Создаем суперадмина...")
            # Создаем суперадмина
            user_data = AdminUserCreate(
                username=username,
                email=email,
                password=password,
                confirm_password=password,
                is_active=True,
                is_superuser=True
            )
            
            new_user = await admin_user.create(db, user_data)
            
            print(f"\n✅ Суперадмин '{new_user.username}' создан успешно!")
            print(f"   ID: {new_user.id}")
            print(f"   Email: {new_user.email}")
            print(f"   Создан: {new_user.created_at}")
            
            print(f"\n🔑 Данные для входа:")
            print(f"   Username: {username}")
            print(f"   Password: [ваш пароль]")
            print(f"   URL: POST /admin-api/auth/login")
            
        except Exception as e:
            print(f"❌ Ошибка при создании суперадмина: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()
        finally:
            # Закрываем сессию через генератор
            try:
                await db_generator.aclose()
            except:
                pass
        
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        import traceback
        traceback.print_exc()

async def quick_create_admin():
    """Быстрое создание админа с тестовыми данными"""
    print("=== Быстрое создание тестового админа ===")
    
    try:
        from app.deps import get_db
        from app.crud.admin import admin_user
        from app.schemas.admin import AdminUserCreate
        
        username = "admin"
        email = "admin@example.com"
        password = "admin123"
        
        # Используем функцию get_db()
        db_generator = get_db()
        db = await db_generator.__anext__()
        
        try:
            # Проверяем что админа еще нет
            existing = await admin_user.get_by_username(db, username)
            if existing:
                print(f"⚠️  Админ '{username}' уже существует")
                print(f"   ID: {existing.id}")
                print(f"   Email: {existing.email}")
                print(f"   Активен: {'Да' if existing.is_active else 'Нет'}")
                print(f"   Суперадмин: {'Да' if existing.is_superuser else 'Нет'}")
                print(f"\n🔑 Данные для входа:")
                print(f"   Username: {username}")
                print(f"   Password: {password}")
                return
            
            # Создаем тестового админа
            user_data = AdminUserCreate(
                username=username,
                email=email,
                password=password,
                confirm_password=password,
                is_active=True,
                is_superuser=True
            )
            
            new_user = await admin_user.create(db, user_data)
            
            print(f"✅ Тестовый админ создан!")
            print(f"   ID: {new_user.id}")
            print(f"   Username: {username}")
            print(f"   Password: {password}")
            print(f"   Email: {email}")
            print(f"\n🔑 Можете войти в админку:")
            print(f"   POST /admin-api/auth/login")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()
        finally:
            try:
                await db_generator.aclose()
            except:
                pass
            
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        import traceback
        traceback.print_exc()

async def list_admins():
    """Показать список существующих админов"""
    print("=== Список админов ===")
    
    try:
        from app.deps import get_db
        from app.crud.admin import admin_user
        
        db_generator = get_db()
        db = await db_generator.__anext__()
        
        try:
            admins = await admin_user.get_multi(db, limit=100)
            if not admins:
                print("Админов не найдено")
                return
            
            print(f"Найдено админов: {len(admins)}")
            print("-" * 50)
            for admin in admins:
                status = "✅ активен" if admin.is_active else "❌ неактивен"
                role = "👑 суперадмин" if admin.is_superuser else "🔧 админ"
                last_login = admin.last_login.strftime("%Y-%m-%d %H:%M") if admin.last_login else "никогда"
                
                print(f"ID: {admin.id}")
                print(f"Username: {admin.username}")
                print(f"Email: {admin.email}")
                print(f"Статус: {status}")
                print(f"Роль: {role}")
                print(f"Последний вход: {last_login}")
                print(f"Неудачных попыток: {admin.failed_login_attempts}")
                print("-" * 50)
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                await db_generator.aclose()
            except:
                pass
            
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "quick":
            asyncio.run(quick_create_admin())
        elif sys.argv[1] == "list":
            asyncio.run(list_admins())
        else:
            print("Доступные команды:")
            print("  python create_superuser.py         - интерактивное создание")
            print("  python create_superuser.py quick   - быстрое создание (admin/admin123)")
            print("  python create_superuser.py list    - показать список админов")
    else:
        asyncio.run(create_superuser())