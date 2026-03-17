"""
Admin Bucket Management Routes

Routes for managing buckets: listing, viewing details, updating fees, and statistics.
"""

from flask import render_template, jsonify, request, session
from utils.auth_utils import admin_required
from . import admin_bp


@admin_bp.route('/api/buckets')
@admin_required
def get_all_buckets():
    """
    Get paginated list of all unique buckets with analytics.

    Query params:
        - page: Page number (default 1)
        - per_page: Items per page (default 50, max 100)
        - search: Search term for bucket name/spec
        - metal: Filter by metal type
        - sort: Sort field (bucket_id, metal, listings, bids, volume)
        - order: Sort order (asc, desc)
    """
    from database import get_db_connection

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    search = request.args.get('search', '').strip()
    metal_filter = request.args.get('metal', '').strip()
    sort_field = request.args.get('sort', 'bucket_id')
    sort_order = request.args.get('order', 'asc')

    offset = (page - 1) * per_page

    conn = get_db_connection()
    try:
        # Build base query for unique buckets with aggregated data
        base_query = '''
            SELECT
                c.bucket_id,
                c.metal,
                c.product_type,
                c.product_line,
                c.weight,
                c.purity,
                c.platform_fee_type,
                c.platform_fee_value,
                c.fee_updated_at,
                COUNT(DISTINCT l.id) FILTER (WHERE l.active = 1 AND l.quantity > 0) as active_listings,
                COUNT(DISTINCT b.id) FILTER (WHERE b.active = 1 AND b.status IN ('Open', 'Partially Filled')) as active_bids
            FROM categories c
            LEFT JOIN listings l ON l.category_id = c.id
            LEFT JOIN bids b ON b.category_id = c.id
            WHERE c.bucket_id IS NOT NULL
        '''

        params = []

        # Add search filter
        if search:
            base_query += ''' AND (
                c.metal LIKE ? OR
                c.product_type LIKE ? OR
                c.product_line LIKE ? OR
                c.weight LIKE ? OR
                CAST(c.bucket_id AS TEXT) LIKE ?
            )'''
            search_term = f'%{search}%'
            params.extend([search_term] * 5)

        # Add metal filter
        if metal_filter:
            base_query += ' AND c.metal = ?'
            params.append(metal_filter)

        # Group by bucket_id to get unique buckets
        base_query += ' GROUP BY c.bucket_id'

        # Add sorting
        valid_sort_fields = {
            'bucket_id': 'c.bucket_id',
            'metal': 'c.metal',
            'listings': 'active_listings',
            'bids': 'active_bids',
            'fee': 'c.platform_fee_value'
        }
        sort_col = valid_sort_fields.get(sort_field, 'c.bucket_id')
        sort_dir = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
        base_query += f' ORDER BY {sort_col} {sort_dir}'

        # Get total count for pagination
        count_query = f'''
            SELECT COUNT(*) as total FROM (
                SELECT c.bucket_id
                FROM categories c
                WHERE c.bucket_id IS NOT NULL
                {'AND (c.metal LIKE ? OR c.product_type LIKE ? OR c.product_line LIKE ? OR c.weight LIKE ? OR CAST(c.bucket_id AS TEXT) LIKE ?)' if search else ''}
                {'AND c.metal = ?' if metal_filter else ''}
                GROUP BY c.bucket_id
            )
        '''
        count_params = []
        if search:
            count_params.extend([f'%{search}%'] * 5)
        if metal_filter:
            count_params.append(metal_filter)

        total_count = conn.execute(count_query, count_params).fetchone()['total']

        # Add pagination
        base_query += ' LIMIT ? OFFSET ?'
        params.extend([per_page, offset])

        # Execute query
        buckets = conn.execute(base_query, params).fetchall()

        # Fetch current global default fee for display label
        global_fee_row = conn.execute(
            "SELECT fee_value FROM fee_config WHERE config_key = 'default_platform_fee' AND active = 1"
        ).fetchone()
        if global_fee_row:
            global_fee_pct = float(global_fee_row['fee_value'])
        else:
            from services.ledger_constants import DEFAULT_PLATFORM_FEE_VALUE
            global_fee_pct = DEFAULT_PLATFORM_FEE_VALUE

        # Format results
        buckets_list = []
        for bucket in buckets:
            # Build bucket name from specs
            name_parts = []
            if bucket['weight']:
                name_parts.append(bucket['weight'])
            if bucket['metal']:
                name_parts.append(bucket['metal'])
            if bucket['product_line']:
                name_parts.append(bucket['product_line'])
            elif bucket['product_type']:
                name_parts.append(bucket['product_type'])

            bucket_name = ' '.join(name_parts) if name_parts else f"Bucket #{bucket['bucket_id']}"

            # Format fee display
            if bucket['platform_fee_type'] and bucket['platform_fee_value'] is not None:
                if bucket['platform_fee_type'] == 'percent':
                    fee_display = f"{bucket['platform_fee_value']}%"
                else:
                    fee_display = f"${bucket['platform_fee_value']:.2f}"
            else:
                fee_display = f'Default ({global_fee_pct:g}%)'

            buckets_list.append({
                'bucket_id': bucket['bucket_id'],
                'name': bucket_name,
                'metal': bucket['metal'] or 'Unknown',
                'product_type': bucket['product_type'],
                'product_line': bucket['product_line'],
                'weight': bucket['weight'],
                'purity': bucket['purity'],
                'active_listings': bucket['active_listings'] or 0,
                'active_bids': bucket['active_bids'] or 0,
                'fee_type': bucket['platform_fee_type'],
                'fee_value': bucket['platform_fee_value'],
                'fee_display': fee_display,
                'fee_updated_at': bucket['fee_updated_at']
            })

        # Get distinct metals for filter dropdown
        metals = conn.execute('''
            SELECT DISTINCT metal FROM categories
            WHERE bucket_id IS NOT NULL AND metal IS NOT NULL
            ORDER BY metal
        ''').fetchall()
        metal_options = [m['metal'] for m in metals]

        return jsonify({
            'success': True,
            'buckets': buckets_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'total_pages': (total_count + per_page - 1) // per_page,
                'has_next': offset + per_page < total_count,
                'has_prev': page > 1
            },
            'filters': {
                'metals': metal_options
            }
        })

    except Exception as e:
        print(f"Error getting buckets: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/buckets/<int:bucket_id>')
@admin_required
def get_bucket_details(bucket_id):
    """Get detailed analytics and configuration for a specific bucket"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        # Get bucket info from first matching category
        bucket = conn.execute('''
            SELECT
                c.bucket_id,
                c.metal,
                c.product_type,
                c.product_line,
                c.weight,
                c.purity,
                c.mint,
                c.finish,
                c.grade,
                c.platform_fee_type,
                c.platform_fee_value,
                c.fee_updated_at,
                MIN(c.id) as first_category_id
            FROM categories c
            WHERE c.bucket_id = ?
            GROUP BY c.bucket_id
        ''', (bucket_id,)).fetchone()

        if not bucket:
            return jsonify({'success': False, 'error': 'Bucket not found'}), 404

        # Get listing stats
        listing_stats = conn.execute('''
            SELECT
                COUNT(*) as total_listings,
                COUNT(*) FILTER (WHERE l.active = 1 AND l.quantity > 0) as active_listings,
                SUM(l.quantity) FILTER (WHERE l.active = 1) as total_quantity
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ?
        ''', (bucket_id,)).fetchone()

        # Get bid stats
        bid_stats = conn.execute('''
            SELECT
                COUNT(*) as total_bids,
                COUNT(*) FILTER (WHERE b.active = 1 AND b.status IN ('Open', 'Partially Filled')) as active_bids,
                SUM(b.remaining_quantity) FILTER (WHERE b.active = 1) as total_bid_quantity
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE c.bucket_id = ?
        ''', (bucket_id,)).fetchone()

        # Get order/transaction stats from order_items_ledger
        order_stats = conn.execute('''
            SELECT
                COUNT(DISTINCT oil.order_id) as total_orders,
                COALESCE(SUM(oil.gross_amount), 0) as total_volume,
                COALESCE(AVG(oil.unit_price), 0) as avg_sale_price,
                COALESCE(SUM(oil.fee_amount), 0) as total_fees_collected
            FROM order_items_ledger oil
            JOIN listings l ON oil.listing_id = l.id
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id = ?
        ''', (bucket_id,)).fetchone()

        # Get price history (last 30 days)
        price_history = conn.execute('''
            SELECT
                date(bph.timestamp) as date,
                AVG(bph.best_ask_price) as avg_price,
                MIN(bph.best_ask_price) as min_price,
                MAX(bph.best_ask_price) as max_price
            FROM bucket_price_history bph
            WHERE bph.bucket_id = ?
              AND bph.timestamp >= datetime('now', '-30 days')
            GROUP BY date(bph.timestamp)
            ORDER BY date(bph.timestamp) ASC
        ''', (bucket_id,)).fetchall()

        # Get fee change history
        fee_history = []
        try:
            fee_events = conn.execute('''
                SELECT
                    bfe.*,
                    u.username as admin_username
                FROM bucket_fee_events bfe
                JOIN users u ON bfe.admin_id = u.id
                WHERE bfe.bucket_id = ?
                ORDER BY bfe.created_at DESC
                LIMIT 10
            ''', (bucket_id,)).fetchall()
            fee_history = [dict(e) for e in fee_events]
        except Exception:
            # Table may not exist yet
            pass

        # Build bucket name
        name_parts = []
        if bucket['weight']:
            name_parts.append(bucket['weight'])
        if bucket['metal']:
            name_parts.append(bucket['metal'])
        if bucket['product_line']:
            name_parts.append(bucket['product_line'])
        elif bucket['product_type']:
            name_parts.append(bucket['product_type'])
        bucket_name = ' '.join(name_parts) if name_parts else f"Bucket #{bucket_id}"

        return jsonify({
            'success': True,
            'bucket': {
                'bucket_id': bucket['bucket_id'],
                'name': bucket_name,
                'metal': bucket['metal'],
                'product_type': bucket['product_type'],
                'product_line': bucket['product_line'],
                'weight': bucket['weight'],
                'purity': bucket['purity'],
                'mint': bucket['mint'],
                'finish': bucket['finish'],
                'grade': bucket['grade'],
                'fee_config': {
                    'fee_type': bucket['platform_fee_type'],
                    'fee_value': bucket['platform_fee_value'],
                    'updated_at': bucket['fee_updated_at']
                }
            },
            'stats': {
                'listings': {
                    'total': listing_stats['total_listings'] or 0,
                    'active': listing_stats['active_listings'] or 0,
                    'total_quantity': listing_stats['total_quantity'] or 0
                },
                'bids': {
                    'total': bid_stats['total_bids'] or 0,
                    'active': bid_stats['active_bids'] or 0,
                    'total_bid_quantity': bid_stats['total_bid_quantity'] or 0
                },
                'orders': {
                    'total_orders': order_stats['total_orders'] or 0,
                    'total_volume': round(order_stats['total_volume'] or 0, 2),
                    'avg_sale_price': round(order_stats['avg_sale_price'] or 0, 2),
                    'total_fees_collected': round(order_stats['total_fees_collected'] or 0, 2)
                }
            },
            'price_history': [dict(p) for p in price_history],
            'fee_history': fee_history
        })

    except Exception as e:
        print(f"Error getting bucket details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/api/buckets/<int:bucket_id>/fee', methods=['POST'])
@admin_required
def update_bucket_fee(bucket_id):
    """
    Update the platform fee configuration for a bucket.

    This only affects FUTURE orders. Existing orders retain their snapshotted fees.

    Request body:
        - fee_type: 'percent' or 'flat'
        - fee_value: float
    """
    from services.ledger_service import LedgerService

    data = request.get_json() or {}
    fee_type = data.get('fee_type')
    fee_value = data.get('fee_value')

    # Validate inputs
    if fee_type not in ('percent', 'flat'):
        return jsonify({
            'success': False,
            'error': "fee_type must be 'percent' or 'flat'"
        }), 400

    try:
        fee_value = float(fee_value)
    except (TypeError, ValueError):
        return jsonify({
            'success': False,
            'error': 'fee_value must be a number'
        }), 400

    if fee_value < 0:
        return jsonify({
            'success': False,
            'error': 'fee_value must be >= 0'
        }), 400

    if fee_type == 'percent' and fee_value > 100:
        return jsonify({
            'success': False,
            'error': 'Percent fee cannot exceed 100%'
        }), 400

    admin_id = session.get('user_id')

    try:
        success = LedgerService.update_bucket_fee(
            bucket_id=bucket_id,
            fee_type=fee_type,
            fee_value=fee_value,
            admin_id=admin_id
        )

        if success:
            # Format fee display for response
            if fee_type == 'percent':
                fee_display = f"{fee_value}%"
            else:
                fee_display = f"${fee_value:.2f}"

            return jsonify({
                'success': True,
                'message': f'Bucket fee updated to {fee_display}',
                'fee_config': {
                    'fee_type': fee_type,
                    'fee_value': fee_value,
                    'fee_display': fee_display
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update bucket fee'
            }), 500

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"Error updating bucket fee: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/buckets/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_buckets():
    """
    Delete (dissolve) multiple buckets by nullifying their bucket_id on categories.
    Associated listings and bids are deactivated.

    Request body:
        - bucket_ids: list of bucket IDs to delete
    """
    from database import get_db_connection

    data = request.get_json() or {}
    bucket_ids = data.get('bucket_ids', [])

    if not bucket_ids or not isinstance(bucket_ids, list):
        return jsonify({'success': False, 'error': 'bucket_ids must be a non-empty list'}), 400

    # Sanitize: ensure all are integers
    try:
        bucket_ids = [int(bid) for bid in bucket_ids]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'All bucket_ids must be integers'}), 400

    conn = get_db_connection()
    try:
        placeholders = ','.join('?' * len(bucket_ids))

        # Deactivate listings in these buckets
        conn.execute(f'''
            UPDATE listings SET active = 0
            WHERE category_id IN (
                SELECT id FROM categories WHERE bucket_id IN ({placeholders})
            )
        ''', bucket_ids)

        # Cancel bids in these buckets
        conn.execute(f'''
            UPDATE bids SET active = 0, status = 'Cancelled'
            WHERE category_id IN (
                SELECT id FROM categories WHERE bucket_id IN ({placeholders})
            )
        ''', bucket_ids)

        # Dissolve the bucket grouping
        conn.execute(f'''
            UPDATE categories SET bucket_id = NULL
            WHERE bucket_id IN ({placeholders})
        ''', bucket_ids)

        conn.commit()
        return jsonify({'success': True, 'deleted': len(bucket_ids)})

    except Exception as e:
        print(f"Error bulk-deleting buckets: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@admin_bp.route('/buckets/<int:bucket_id>')
@admin_required
def bucket_detail_page(bucket_id):
    """Render the admin bucket detail page"""
    return render_template('admin/bucket_detail.html', bucket_id=bucket_id)


@admin_bp.route('/api/buckets/stats')
@admin_required
def get_bucket_stats():
    """Get aggregate statistics for the buckets dashboard"""
    from database import get_db_connection

    conn = get_db_connection()
    try:
        stats = {}

        # Total unique buckets
        result = conn.execute('''
            SELECT COUNT(DISTINCT bucket_id) as count
            FROM categories
            WHERE bucket_id IS NOT NULL
        ''').fetchone()
        stats['total_buckets'] = result['count']

        # Buckets with custom fees
        result = conn.execute('''
            SELECT COUNT(DISTINCT bucket_id) as count
            FROM categories
            WHERE bucket_id IS NOT NULL
              AND platform_fee_type IS NOT NULL
              AND platform_fee_value IS NOT NULL
        ''').fetchone()
        stats['buckets_with_custom_fees'] = result['count']

        # Buckets by metal
        metals = conn.execute('''
            SELECT metal, COUNT(DISTINCT bucket_id) as count
            FROM categories
            WHERE bucket_id IS NOT NULL AND metal IS NOT NULL
            GROUP BY metal
            ORDER BY count DESC
        ''').fetchall()
        stats['buckets_by_metal'] = {m['metal']: m['count'] for m in metals}

        # Total active listings across all buckets
        result = conn.execute('''
            SELECT COUNT(*) as count
            FROM listings l
            JOIN categories c ON l.category_id = c.id
            WHERE c.bucket_id IS NOT NULL AND l.active = 1 AND l.quantity > 0
        ''').fetchone()
        stats['total_active_listings'] = result['count']

        # Total active bids
        result = conn.execute('''
            SELECT COUNT(*) as count
            FROM bids b
            JOIN categories c ON b.category_id = c.id
            WHERE c.bucket_id IS NOT NULL
              AND b.active = 1
              AND b.status IN ('Open', 'Partially Filled')
        ''').fetchone()
        stats['total_active_bids'] = result['count']

        return jsonify({
            'success': True,
            'stats': stats
        })

    except Exception as e:
        print(f"Error getting bucket stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
